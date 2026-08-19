
class ContextualProcessor:
    """
    Advanced processing pipeline: ordering, synthesis method, clustering,
    article generation, and final synthesis.
    """
    def __init__(self, query: str, chunks: List[str], project_names: List[str],
                 llm, settings: dict, progress_callback=None):
        self.query = query
        self.chunks = chunks
        self.project_names = project_names
        self.llm = llm
        self.settings = settings
        self.progress_callback = progress_callback
        self.temperature = settings.get('temperature', 0.7)
        self.top_p = settings.get('top_p', 0.9)
        self.batch_size = settings.get('batch_size', 5)
        self.max_tokens = settings.get('max_tokens', 500)
        self.order = settings.get('order', 'Most Relevant First')
        self.synthesis = settings.get('synthesis', 'Contextual Linking')
        self.cluster_count = settings.get('cluster_count', 3)
        self.drop_threshold = settings.get('drop_threshold', 0.3)

        # Step 1: Order chunks
        self.ordered_chunks = self._order_chunks()
        self.project_names_ordered = self._order_project_names()

        # Step 2: Process batches with chosen synthesis
        self.summaries = self._process_batches()

        # Step 3: Cluster summaries
        self.clusters = self._cluster_summaries()

        # Step 4: Generate articles from clusters
        self.articles = self._generate_articles()

        # Step 5: Final synthesis
        self.final_answer = self._final_synthesis()

    def _order_chunks(self) -> List[str]:
        """Order chunks according to user setting."""
        if self.order == 'Most Relevant First':
            scorer = MLRelevanceScorer(self.chunks, self.query)
            scored = [(chunk, scorer.score_chunk(chunk)) for chunk in self.chunks]
            scored.sort(key=lambda x: x[1], reverse=True)
            return [chunk for chunk, _ in scored]
        elif self.order == 'Least Relevant First':
            scorer = MLRelevanceScorer(self.chunks, self.query)
            scored = [(chunk, scorer.score_chunk(chunk)) for chunk in self.chunks]
            scored.sort(key=lambda x: x[1])
            return [chunk for chunk, _ in scored]
        elif self.order == 'A-Z':
            return self.chunks
        elif self.order == 'Z-A':
            return list(reversed(self.chunks))
        else:
            return self.chunks

    def _order_project_names(self) -> List[str]:
        chunk_to_project = {}
        for i, chunk in enumerate(self.chunks):
            chunk_to_project[chunk] = self.project_names[i]
        return [chunk_to_project[chunk] for chunk in self.ordered_chunks]

    def _process_batches(self) -> List[str]:
        summaries = []
        total_chunks = len(self.ordered_chunks)
        total_batches = (total_chunks + self.batch_size - 1) // self.batch_size
        last_chunk = ""

        for batch_num in range(total_batches):
            start = batch_num * self.batch_size
            end = min(start + self.batch_size, total_chunks)
            batch = self.ordered_chunks[start:end]
            batch_projects = self.project_names_ordered[start:end]

            if self.synthesis == 'Contextual Linking' and last_chunk:
                batch_with_context = [last_chunk] + batch
            else:
                batch_with_context = batch

            context = '\n\n'.join(batch_with_context)

            if self.synthesis == 'Summarization':
                prompt = self._summarization_prompt(context, batch_num+1, total_batches)
            elif self.synthesis == 'Claim Listing':
                prompt = self._claim_listing_prompt(context, summaries, batch_num+1, total_batches)
            else:  # Contextual Linking
                prev_summary = summaries[-1] if summaries else "None"
                prompt = self._contextual_linking_prompt(context, prev_summary, batch_num+1, total_batches)

            response = self._call_llm(prompt, max_tokens=100)
            if response:
                summaries.append(response)
                if self.synthesis == 'Contextual Linking' and batch:
                    last_chunk = batch[-1]

                if self.progress_callback:
                    self.progress_callback('batch', batch_num+1, total_batches, response, batch_projects[0] if batch_projects else '')

        return summaries

    def _summarization_prompt(self, context: str, batch_num: int, total: int) -> str:
        return f"""Summarize the key points from the following text (batch {batch_num} of {total}):

{context}

Provide a concise summary (4-10 sentences)."""

    def _claim_listing_prompt(self, context: str, previous_summaries: List[str], batch_num: int, total: int) -> str:
        prev_claims = '\n'.join(previous_summaries) if previous_summaries else "None"
        return f"""List every unique claim or fact from the following text (batch {batch_num} of {total}) that is NOT already mentioned in the previous claims.

Previous claims:
{prev_claims}

New text:
{context}

List each new claim as a separate sentence. Do not repeat previous claims."""

    def _contextual_linking_prompt(self, context: str, prev_summary: str, batch_num: int, total: int) -> str:
        return f"""Given the previous summary of earlier information:
{prev_summary}

Now read the new text (batch {batch_num} of {total}):
{context}

Identify any new insights, concepts, or ideas that are NOT covered in the previous summary. Provide a brief summary of these new elements (2-10 sentences). Focus only on what is novel."""

    def _call_llm(self, prompt: str, max_tokens: int) -> str:
        try:
            response = self.llm(
                prompt,
                max_tokens=max_tokens,
                temperature=self.temperature,
                top_p=self.top_p,
                stop=["###", "---", "```"]
            )
            content = response['choices'][0]['text'].strip()
            return content if content else ""
        except Exception as e:
            print(f"⚠️ LLM call error: {e}")
            return ""

    def _cluster_summaries(self) -> List[List[str]]:
        if not self.summaries:
            return []

        # Score summaries for relevance to query to find anchors
        scorer = MLRelevanceScorer(self.summaries, self.query)
        scored = [(summary, scorer.score_chunk(summary)) for summary in self.summaries]
        scored.sort(key=lambda x: x[1], reverse=True)

        anchors = scored[:self.cluster_count]
        anchor_indices = [self.summaries.index(summary) for summary, _ in anchors]

        # Create vectorizer for computing similarity between summaries
        from sklearn.feature_extraction.text import TfidfVectorizer
        vectorizer = TfidfVectorizer(max_features=100, stop_words='english')
        summary_vectors = vectorizer.fit_transform(self.summaries)

        clusters = []
        for anchor_idx in anchor_indices:
            cluster = [self.summaries[anchor_idx]]
            anchor_vector = summary_vectors[anchor_idx]

            # Expand backwards
            idx = anchor_idx - 1
            while idx >= 0:
                sim = cosine_similarity(anchor_vector, summary_vectors[idx])[0][0]
                if sim < self.drop_threshold:
                    break
                cluster.insert(0, self.summaries[idx])
                idx -= 1

            # Expand forwards
            idx = anchor_idx + 1
            while idx < len(self.summaries):
                sim = cosine_similarity(anchor_vector, summary_vectors[idx])[0][0]
                if sim < self.drop_threshold:
                    break
                cluster.append(self.summaries[idx])
                idx += 1

            clusters.append(cluster)

        return clusters

    def _generate_articles(self) -> List[str]:
        articles = []
        for i, cluster in enumerate(self.clusters):
            cluster_text = '\n\n'.join(cluster)
            prompt = f"""Write a coherent article based on the following insights (Cluster {i+1}).

Insights:
{cluster_text}

The article should flow logically and cover all the key points. Keep it concise but comprehensive."""
            article = self._call_llm(prompt, max_tokens=400)
            if article:
                articles.append(article)
                if self.progress_callback:
                    self.progress_callback('article', i+1, len(self.clusters), article, '')
        return articles

    def _final_synthesis(self) -> str:
        if not self.articles:
            return "No articles generated."

        scorer = MLRelevanceScorer(self.articles, self.query)
        scored = [(article, scorer.score_chunk(article)) for article in self.articles]
        scored.sort(key=lambda x: x[1])  # least to most relevant

        final_text = '\n\n'.join([article for article, _ in scored])
        prompt = f"""Synthesize the following articles into a single, comprehensive final answer to the query: "{self.query}".

Articles (ordered from least to most relevant):
{final_text}

Create a final answer that integrates all the information, highlights the most important points, and provides a clear, structured response."""
        final = self._call_llm(prompt, max_tokens=600)
        return final if final else final_text
