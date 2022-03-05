from tqdm import tqdm
import json
import numpy as np
from densephrases import DensePhrases


# Arguments: Presently hard-coded, Add argparse later on
top_k = 2
n_sel = 2
load_dir = 'princeton-nlp/densephrases-multi-query-multi'
dump_dir = '/home/nishantraj_umass_edu/DAQuA-Difficulty-Aware-Question-Answering/DPhrases/outputs/densephrases-multi_wiki-20181220/dump'
idx_name = 'start/1048576_flat_OPQ96_small'
device = 'cpu'
ret_meta = True
ret_unit='phrase'
out_file = 'data.json'

# Query List to be updated based on a function to read json validation files and get list of queries after reading
query_list = ["What government position was held by the woman who portrayed Corliss Archer in the film Kiss and Tell?",\
"Who was known by his stage name Aladin and helped organizations improve their performance as a consultant?"]


def load_densephrase_module(load_dir= load_dir, dump_dir= dump_dir, index_name= idx_name, device=device):
    """
    Load Dense Phrases module
    """
    model = DensePhrases(load_dir= load_dir, dump_dir= dump_dir, index_name= idx_name, device=device)
    return model 

def get_first_hop_phrase_score_list(metadata, top_k):
    """
    Get list of scores retrieved from first hop. Note if there are [q1, q2] queries and 
    we requested 2 phrases (top_k) corresponding to these i.e. [[s11,s12],[s21,s22]]
    """
    phrase_score_list = []
    for i in tqdm(range(len(metadata))):
        interim_scores = []
        for j in range(top_k):
            interim_scores.append(metadata[i][j]['score'])
        phrase_score_list.append(interim_scores)
    return phrase_score_list

def create_new_query(query_list, top_k, phrases):
    """
    Add query to the first hop retrievals and treat them as queries for second hop retrievals
    """
    all_query_pairs = [] 
    for query_num in tqdm(range(len(query_list))):
        interim_comb = []
        for sub_phrase_num in range(top_k):
            interim_comb.append(phrases[query_num][sub_phrase_num] + " "+ query_list[query_num])
        all_query_pairs.append(interim_comb)
    
    # Returns a flattened query list for second hop retrieval
    flat_second_hop_qlist = [query for blist in all_query_pairs for query in blist]

    return flat_second_hop_qlist


def get_second_hop_retrieval(hop_phrases, hop_metadata, n_ins, top_k):
    """
    Returns scores and phrases retrieved as a result of retrieval from second hop. 
    Required for deciding best chain for the reader module
    """
    hop_phrases_flat          = [phrase_val for li in hop_phrases for phrase_val in li]
    hop_phrase_score_flat     = [sub['score'] for mdata in hop_metadata for sub in mdata]
    phrase_sc_2               = np.array(hop_phrase_score_flat).reshape((n_ins, top_k, top_k))
    phrase_arr_2              = np.array(hop_phrases_flat).reshape((n_ins, top_k, top_k))

    return phrase_sc_2, phrase_arr_2


def get_top_chains(scores_1, scores_2, doc_id_1, doc_id_2, top_k, n_sel):
    
    """
    Get the scores for a single question at hop 1 and hop 2 and for corresponding phrase combination,
    return the combination of phrase at hop 1 and hop 2 that gave best overall score summation.
    """
    
    path_scores =  np.expand_dims(scores_1, axis=2) + scores_2
    search_scores = path_scores[0]
    ranked_pairs = np.vstack(np.unravel_index(np.argsort(search_scores.ravel())[::-1],(top_k,top_k))).transpose()
    chains = []
    for _ in range(n_sel):
        path_ids = ranked_pairs[_]
        did_1 = doc_id_1[0][path_ids[0]]
        did_2 = doc_id_2[0][path_ids[0]][path_ids[1]]
        chains.append([did_1,did_2])

    return chains

def run_chain_all_queries(query_list, phrase_sc_1, phrase_sc_2, phrase_arr_1, phrase_arr_2, top_k, n_sel):
    """
    For a given query, find the # of n_sel chains based on top_k phrases from Dense Phrases module 
    """
    qchain_dict = {}
    for num_q in range(len(query_list)):
        
        # Get scores and phrase combinations here 
        scores_1 = np.array(phrase_sc_1[num_q]).reshape(1, top_k)
        scores_2 = np.array(phrase_sc_2[num_q]).reshape(1, top_k, top_k)
        doc_id_1 = np.array(phrase_arr_1[num_q]).reshape(1, top_k)
        doc_id_2 = np.array(phrase_arr_2[num_q]).reshape(1, top_k, top_k)
        
        # Use Get Top Chain Function to retrieve best chains for this question
        chain  = get_top_chains(scores_1, scores_2, doc_id_1, doc_id_2, top_k, n_sel)
        
        qchain_dict[query_list[num_q]] = chain
    
    return qchain_dict

if __name__ == "__main__":

    # Load the DensePhrases module 
    print("Loading DensePhrases module, please wait for some time")
    model = load_densephrase_module(load_dir= load_dir, dump_dir= dump_dir, index_name= idx_name, device=device)

    # Total Number of Queries
    n_ins = len(query_list)

    # Run the model to retrieve the first hop of phrases and their corresponding scores
    print("Running DensePhrases module for first hop phrase retrieval ...")
    phrases, metadata = model.search(query_list, retrieval_unit=ret_unit, top_k=top_k, return_meta= ret_meta)

    # Get phrase scores separately from metadata for first hop
    phrase_sc_1 = get_first_hop_phrase_score_list(metadata, top_k)

    # Get new query combinations for second hop retrieval from DensePhrases module
    flat_second_hop_qlist  = create_new_query(query_list, top_k, phrases)

    # Run second hop retrieval from DensePhrases module
    print("Running second hop of phrase retrieval")
    hop_phrases, hop_metadata = model.search(flat_second_hop_qlist, retrieval_unit= ret_unit, top_k=top_k, return_meta= ret_meta)

    # Get score and phrase list from second retrieval for evidence chain extraction
    phrase_sc_2, phrase_arr_2 = get_second_hop_retrieval(hop_phrases, hop_metadata, n_ins, top_k)
    
    print("Creating final dictionary")
    # Get final chain of best n_sel queries for each question
    qchain_dict = run_chain_all_queries(query_list, phrase_sc_1, phrase_sc_2, phrases, phrase_arr_2, top_k, n_sel)

    # Dump information inside a JSON file
    with open(out_file, 'w') as fp:
        json.dump(qchain_dict, fp,  indent=4)

    print("Run Complete")

