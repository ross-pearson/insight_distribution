import os
import json
import requests
import logging
import time
import pickle

class RagUtils:
    def __init__(self, cache_file="rag_cache.pkl", cache_size=100):
        self.rag_endpoint = os.getenv("RAG_ENDPOINT", "http://development.dhi-ai.com:5000/rag")
        self.source_of_request = os.getenv("SOURCE_OF_REQUEST", "insight_distribution")
        self.user_name = os.getenv("USER_NAME", "insight_distribution")
        self.logger = logging.getLogger(__name__)
        self.cache_size = cache_size
        self.cache_file = cache_file
        self.cache = self._load_cache_from_disk()

    def ask_question(self, question):
        # Check if the question is in the cache
        if question in self.cache:
            self.logger.info(f"Returning cached answer for question: {question}")
            return self.cache[question]

        self.logger.info(f"Asking RAG question: {question}")
        form = {
            "prompt": question,
            "source_of_request": self.source_of_request,
            "user_name": self.user_name,
        }

        try:
            self.logger.info("Sending request to RAG endpoint...")
            response = requests.post(self.rag_endpoint, data=form)

            if response.status_code in [200, 201]:
                self.logger.info(f"Received response with status code {response.status_code}. Processing response...")

                response_str = response.content.decode("utf-8")
                lines = response_str.split("\n")

                result = None
                for line in reversed(lines):
                    if line.startswith("data: "):
                        json_str = line[6:]  # Remove the "data: " prefix
                        try:
                            json_obj = json.loads(json_str)
                            if "answer" in json_obj:
                                result = json_obj
                                self.logger.info("Found a valid answer in the response.")
                                break
                        except json.JSONDecodeError:
                            self.logger.warning("Failed to decode JSON, continuing with the next line.")
                            continue

                if result:
                    rag_response = result.get("answer", "No response")
                    conversation_id = result.get("conversation_id", None)

                    # Save the result in the cache and persist to disk
                    self._update_cache(question, (rag_response, conversation_id))

                    self.logger.info(f"RAG response successfully retrieved: {rag_response}")
                    return rag_response, conversation_id
                else:
                    self.logger.error("No valid response found in the RAG output.")
                    return "No response", None
            else:
                self.logger.error(f"RAG request failed with status code {response.status_code}. Retrying...")
                time.sleep(1)  # Optional: Add delay before retrying if needed
                return "Request failed", None

        except requests.RequestException as e:
            self.logger.error(f"An error occurred while contacting the RAG endpoint: {e}")
            return "Request error", None

    def _update_cache(self, question, result):
        """Updates the cache with the latest question and result and saves it to disk."""
        if len(self.cache) >= self.cache_size:
            # If the cache is full, remove the oldest item (FIFO)
            oldest_question = next(iter(self.cache))
            del self.cache[oldest_question]
            self.logger.info(f"Cache full. Removed oldest cached entry: {oldest_question}")

        self.cache[question] = result
        self._save_cache_to_disk()
        self.logger.info(f"Cached the result for question: {question}")

    def _load_cache_from_disk(self):
        """Loads the cache from disk if it exists."""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "rb") as f:
                    cache = pickle.load(f)
                self.logger.info("Loaded cache from disk.")
                return cache
            except Exception as e:
                self.logger.error(f"Failed to load cache from disk: {e}")
                return {}
        else:
            self.logger.info("No cache file found. Starting with an empty cache.")
            return {}

    def _save_cache_to_disk(self):
        """Saves the current cache to disk."""
        try:
            with open(self.cache_file, "wb") as f:
                pickle.dump(self.cache, f)
            self.logger.info("Cache saved to disk.")
        except Exception as e:
            self.logger.error(f"Failed to save cache to disk: {e}")

