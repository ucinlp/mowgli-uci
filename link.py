from functools import partial
import hashlib
import json
import logging
from pathlib import Path
import pickle
from typing import Callable, List, Tuple

import autocli
import faiss
import numpy as np
from tqdm import tqdm

from text_to_uri import english_filter, replace_numbers

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

CACHE_DIR = Path('.cache/')


def init_cache():
    if not CACHE_DIR.exists():
        logger.debug(f'Creating cache dir at: {CACHE_DIR}')
        CACHE_DIR.mkdir(parents=True)


def _cache_path(fn, args, kwargs):
    fn_name = fn.__name__
    args_string = ','.join(str(arg) for arg in args)
    kwargs_string = json.dumps(kwargs)
    byte_string = fn_name + args_string + kwargs_string
    hash_object = hashlib.sha1(byte_string.encode())
    return CACHE_DIR / hash_object.hexdigest()


def cache():
    def decorator(fn):
        def load_cached_if_available(*args, **kwargs):
            path = _cache_path(fn, args, kwargs)
            if path.exists():
                logger.debug(f'Loading `{fn.__name__}` output from cache')
                with open(path, 'rb') as f:
                    return pickle.load(f)
            output = fn(*args, **kwargs)
            with open(path, 'wb') as f:
                pickle.dump(output, f)
            return output
        return load_cached_if_available
    return decorator


class Vocab:
    def __init__(self, words) -> None:
        self.idx_to_word = words
        self.word_to_idx = {word: idx for idx, word in enumerate(words)}


@cache()
def read_embedding_file(embedding_file: Path) -> Tuple[Vocab, np.ndarray]:

    logger.debug(f'Reading embeddings from {embedding_file}')

    with open(embedding_file, 'r') as f:
        info = next(f)
        shape = tuple(int(x) for x in info.split())
        embeddings = np.zeros(shape, dtype=np.float32)

        words = []
        for i, line in tqdm(enumerate(f), total=shape[0]):
            word, *embedding = line.split()
            embedding = np.array([float(x) for x in embedding])
            words.append(word)
            embeddings[i] = embedding

    vocab = Vocab(words)

    return vocab, embeddings


def build_index(metric: str, embeddings: np.ndarray) -> faiss.swigfaiss_avx2.Index:

    logger.debug(f'Building search index')

    if metric == 'cosine':
        index = faiss.IndexFlatIP(embeddings.shape[-1])
    elif metric == 'l2':
        index = faiss.IndexFlatL2(embeddings.shape[-1])
    else:
        raise ValueError(f'Bad metric: {metric}')

    index.add(embeddings)

    return index


def generate_instances(dataset: Path):
    with open(dataset, 'r') as f:
        for line in f:
            yield(json.loads(line))


def get_extraction_fn(extraction_strategy: str,
                      ngram_length: int) -> Callable[[List[str], Vocab], List[str]]:
    if extraction_strategy == 'exhaustive':
        return partial(exhaustive_extraction, ngram_length=ngram_length)
    elif extraction_strategy == 'greedy':
        return partial(greedy_extraction, ngram_length=ngram_length)
    else:
        raise ValueError(f'Bad extraction strategy: {extraction_strategy}')


def exhaustive_extraction(tokens: List[str],
                          vocab: Vocab,
                          ngram_length: int) -> List[str]:
    num_tokens = len(tokens)
    out = []
    for n in range(1, ngram_length):
        for i in range(num_tokens - n + 1):
            concept = replace_numbers('_'.join(tokens[i: i+n]))
            if concept in vocab.word_to_idx:
                out.append(concept)
    return out


def greedy_extraction(tokens: List[str],
                      vocab: Vocab,
                      ngram_length: int) -> List[str]:
    out = []
    while len(tokens) > 0:
        for n in range(ngram_length + 1, 0, -1):
            concept = replace_numbers('_'.join(tokens[:n]))
            if concept in vocab.word_to_idx:
                out.append(concept)
                tokens = tokens[n:]
                break
            elif n == 1:
                tokens = tokens[n:]
    return out


@autocli.add_command()
def link(input: Path,
         output: Path,
         embedding_file: Path,
         metric: str = 'cosine',
         extraction_strategy: str = 'exhaustive',
         ngram_length: int = 3,
         num_candidates: int = 5,
         debug: bool = False) -> None:
    """
    Browse the top-k conceptnet candidates for a node.

    Parameters
    ==========
    input : Path
        A jsonl file containing parsed alpha NLI graphs.
    output : Path
        Jsonl file to serialize output to.
    embedding_file : Path
        A txt file containing the embeddings.
    metric: str
        Similarity metric. One of: 'cosine', 'l2'
    extraction_strategy: str
        Approach for extracting concepts from mentions. One of: 'exhaustive', 'greedy'
    ngram_length: int
        Max length of n-grams to consider during concept extraction.
    num_candidates : int
        Number of candidates to display.
    """
    assert metric in {'cosine', 'l2'}
    assert extraction_strategy in {'exhaustive', 'greedy'}

    if debug:
        logger.setLevel(logging.DEBUG)

    init_cache()
    vocab, embeddings = read_embedding_file(embedding_file)
    index = build_index(metric, embeddings)
    extraction_fn = get_extraction_fn(extraction_strategy, ngram_length)

    output_file = open(output, 'w')
    for instance in generate_instances(input):
        output_instance = instance.copy()
        for uri, node in instance['nodes'].items():
            mention = ' '.join(node['phrase'])
            tokens = english_filter([x.lower() for x in node['phrase']])
            concepts = extraction_fn(tokens, vocab)
            concept_ids = np.array([vocab.word_to_idx[concept] for concept in concepts])
            if len(concept_ids) > 0:
                query = np.mean(embeddings[concept_ids], axis=0, keepdims=True)
                scores, candidate_ids = index.search(query, num_candidates)
            else:
                scores = candidate_ids = []

            output_instance['nodes'][uri]['candidates'] = []
            for candidate_id, score in zip(np.nditer(candidate_ids), np.nditer(scores)):
                if '#' in candidate:
                    logger.warning('Encountered a uri containing an #. Due to preprocessing steps '
                                   'used to produce the ConceptNet Numberbatch embeddings this is '
                                   'likely a bad link, and will be skipped.')
                    continue
                candidate = vocab.idx_to_word[candidate_id]
                output_instance['nodes'][uri]['candidates'].append({
                    'uri': '/c/en/' + candidate,  # TODO: Support other KBs
                    'score': score.item()
                })
        output_file.write(json.dumps(output_instance) + '\n')


if __name__ == '__main__':
    autocli.parse_and_run()
