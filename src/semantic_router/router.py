import numpy as np
from sentence_transformers import SentenceTransformer

class SemanticRouter():
    def __init__(self, model_path: str="./weights/Vietnamese_Embedding", model: object=None):
        # self.routes = routes
        if not model:
            self.embedding_model = SentenceTransformer(model_path)
        else:
            self.embedding_model = model
        # self.routesEmbedding = {}
        # self.routesEmbeddingCal = {}

        # for route in self.routes:
        #     self.routesEmbedding[
        #         route.name
        #     ] = self.embedding_model.encode(route.samples)

        # for route in self.routes:
        #     self.routesEmbeddingCal[
        #         route.name
        #     ] = self.routesEmbedding[route.name] / np.linalg.norm(self.routesEmbedding[route.name])

    # def get_routes(self):
    #     return self.routes
    
    def embed(self, samples: list):
        embedded = np.array(list(self.embedding_model.query_embed(samples)))
        embedded = embedded / np.linalg.norm(embedded, axis=1, keepdims=True)
        return embedded.astype(np.float16)
        
    def guide(self, query: str, route_embed: dict):
        scores = []
        for name, embed in route_embed.items():
            sampleEmbedding = np.array(embed)
            sampleEmbedding = np.frombuffer(sampleEmbedding, dtype=np.float16).reshape(len(sampleEmbedding), 1024)

            queryEmbedding = np.array(list(self.embedding_model.query_embed([query])), dtype=np.float16)
            queryEmbedding = queryEmbedding / np.linalg.norm(queryEmbedding, axis=1, keepdims=True)

            # print(sampleEmbedding.shape)
            # print(queryEmbedding.shape)
            # Calculate the cosine similarity of the query embedding with the sample embeddings of the router.
            # print(np.dot(sampleEmbedding, queryEmbedding.T).flatten())
            score = np.mean(np.dot(sampleEmbedding, queryEmbedding.T).flatten())
            scores.append((score, name))

        print(scores)
        scores.sort(reverse=True)
        return scores[0]