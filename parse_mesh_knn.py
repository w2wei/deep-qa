'''
  Parse PubMed abstracts and titles and save resulted matrices for training CNN models.
  Modified on the Severyn's code (https://github.com/aseveryn/deep-qa).
  MeSH terms are selected from KNN articles.

  Updated on June 7, 2016
  @author Wei Wei
'''

import re
import os, string, time
import random
import numpy as np
import cPickle
import subprocess
from collections import defaultdict
from operator import itemgetter

from alphabet import Alphabet
from corpus import loadCorpus
from collections import defaultdict
from nltk.tokenize import sent_tokenize,TreebankWordTokenizer
printable = set(string.printable)
replace_punctuation = string.maketrans(string.punctuation, ' '*len(string.punctuation))
from new_mesh_and_entry_vocab import loadAll
raw_mesh_entry_vocab, mesh_phrase_idx, mesh_phrase_dict, rawMesh_meshAndEntry_dict = loadAll() ## in mesh_phrase_vocab, tokens in phrases are connected with underscores, e.g., rna seq -> rna_seq
raw_mesh_vocab = rawMesh_meshAndEntry_dict.keys()
clean_mesh_vocab = [x[0] for x in rawMesh_meshAndEntry_dict.values()]
# print "human_papillomavirus_16" in clean_mesh_vocab
# print rawMesh_meshAndEntry_dict.get("human_papillomavirus_16")
# print rawMesh_meshAndEntry_dict.get("human papillomavirus 16")
# raw_input("....")
raw_mesh_set = set(raw_mesh_vocab)
clean_mesh_set = set(clean_mesh_vocab)
from knn_data import Data
from pprint import pprint

UNKNOWN_WORD_IDX = 0


print "All modules loaded"

def parser(inText):
    text = filter(lambda x: x in printable, inText) ## remove non-ascii characters
    sent_tokenize_list = sent_tokenize(text.strip().lower(), "english") ## tokenize documents into sentences, lower case

    for sent_idx in xrange(len(sent_tokenize_list)):
        updated_sent = [] ## a modified sentence
        sent_tokenize_list[sent_idx] = sent_tokenize_list[sent_idx].translate(replace_punctuation) ## remove all punctuation
        sent_tokenize_list[sent_idx] = TreebankWordTokenizer().tokenize(sent_tokenize_list[sent_idx]) ## sent_tokenize_list[sent_idx] is a list of unigrams now

        term_idx = 0
        sentLen = len(sent_tokenize_list[sent_idx])
        while term_idx<sentLen:
            flag = 1
            curr_term = sent_tokenize_list[sent_idx][term_idx]
            if mesh_phrase_idx.get(curr_term):
                maxPhraseLen = mesh_phrase_idx.get(curr_term) ## the maximum length of phrase starting with the current term
                for n in xrange(maxPhraseLen,1,-1): ## iterate from n to 2
                    curr_n_gram = " ".join(sent_tokenize_list[sent_idx][term_idx:min(term_idx+n, sentLen)])
                    if mesh_phrase_dict.get(curr_n_gram):
                        updated_sent.append(mesh_phrase_dict.get(curr_n_gram))
                        term_idx+=n # move the pointer
                        flag = 0
                        break
                if flag:
                    updated_sent.append(curr_term)
                    term_idx+=1
            else:
                updated_sent.append(curr_term)
                term_idx+=1
        sent_tokenize_list[sent_idx] = re.sub(r"\b\d+\b", " ", " ".join(updated_sent))## replace isolated digits
    tokenList = " ".join(sent_tokenize_list).split()
    return tokenList

def mesh_parser(termList):
    newTermList = []
    for term in termList:
        text = filter(lambda x: x in printable, term) 
        text = text.translate(replace_punctuation)
        text = " ".join(text.split())
        newTermList.append(text)
    return newTermList

def mesh_parser4Lu_data(text):
    text = re.sub("[-*&]"," ",text)
    mhList = text.split("!")
    mhList = [mh.strip("*") for mh in mhList]
    return mhList

def get_cand_raw_mesh(cand_pmids, raw_nbr_tam):
    cand_mesh_list = []
    for pmid in cand_pmids:
        raw_cand_data = raw_nbr_tam[pmid]
        if len(raw_cand_data)==3:
            raw_cand_mesh = raw_cand_data[2]
        else:
            possible_raw_cand_mesh = raw_cand_data[-1]
            if isinstance(possible_raw_cand_mesh, str):
                raw_cand_mesh = possible_raw_cand_mesh
            else:
                raw_cand_mesh = ''
        cand_mesh = mesh_parser4Lu_data(raw_cand_mesh)
        cand_mesh_list+=cand_mesh
    cand_mesh_list = list(set(cand_mesh_list))
    cand_mesh_list.sort()
    return cand_mesh_list

def load_all_data(raw_train, raw_dev, raw_test, stoplist):
    qids, questions, answers, labels = [], [], [], []
    obj_list = [raw_train, raw_dev, raw_test]
    train_pmids = raw_train.query_pmids
    dev_pmids = raw_dev.query_pmids
    test_pmids = raw_test.query_pmids
    pmid_groups = [train_pmids, dev_pmids, test_pmids]

    for i in range(len(obj_list)):
        pmidList = pmid_groups[i]
        for pmid in pmidList:
            title, abstract, raw_mesh = obj_list[i].query_tam[pmid]
            raw_question = " ".join(title+abstract)
            clean_question = parser(raw_question)
            std_raw_mesh = mesh_parser4Lu_data(raw_mesh) ## gold standard mesh terms, raw term, lower case
            ## select candidates from 20 nearest neighbors
            sorted_nbr_dict = sorted(obj_list[i].nbr_dict[pmid],key=itemgetter(1),reverse=True)[:20]
            cand_pmids = [x[0] for x in sorted_nbr_dict] # 20 nearest neighbor pmids
            ## select candidates from 50 neighbor neighbors
            # cand_pmids = [x[0] for x in obj_list[i].nbr_dict[pmid]] ## candidates from neighbors, from all 50 nbrs
            cand_raw_mesh = get_cand_raw_mesh(cand_pmids, obj_list[i].nbr_tam)
            ## answers
            pos_meshList = list(set(std_raw_mesh)&set(cand_raw_mesh))
            neg_meshList = list(set(cand_raw_mesh)-set(pos_meshList)) ## keep all false terms in candidates
            # if i!=2:
            #     neg_meshList = random.sample(neg_meshList, len(pos_meshList)) # make a neg mesh subset 
            meshNum = len(pos_meshList)+len(neg_meshList) ## answer number for this PMID

            for p_mesh in pos_meshList:
                answer = rawMesh_meshAndEntry_dict.get(p_mesh) # answer may contain None
                if not answer: # if answer==None
                    answer = [p_mesh] # answer is the pseudo mesh term itself
                answers.append(answer)
                qids.append(pmid)
                questions.append(clean_question)
                labels.append(1)

            for n_mesh in neg_meshList:
                answer = rawMesh_meshAndEntry_dict.get(n_mesh) ## clean mesh terms and entry terms
                if not answer: # if answer==None
                    answer = [n_mesh] # answer is the pseudo mesh term itself            
                answers.append(answer) #  answer may contain None
                qids.append(pmid)
                questions.append(clean_question)
                labels.append(0)

    return qids, questions, answers, labels        

def load_data(raw_data, stoplist, idx):
    '''Parse raw MEDLINE records; extract PMID, title, abstract, and MeSH'''
    ## idx=0, train; idx=1, dev; idx=2, test
    qids, questions, answers, labels = [], [], [], []
    pmidList = raw_data.query_pmids

    for pmid in pmidList:
        title, abstract, raw_mesh = raw_data.query_tam[pmid]
        raw_question = " ".join(title+abstract)
        clean_question = parser(raw_question)
        std_raw_mesh = mesh_parser4Lu_data(raw_mesh) ## gold standard mesh terms, raw term, lower case
        ## select candidates from 20 nearest neighbors
        sorted_nbr_dict = sorted(raw_data.nbr_dict[pmid],key=itemgetter(1),reverse=True)[:20] 
        cand_pmids = [x[0] for x in sorted_nbr_dict] # 20 nearest neighbor pmids
        ## select candidates from 50 neighbor neighbors
        # cand_pmids = [x[0] for x in obj_list[i].nbr_dict[pmid]] ## candidates from neighbors, from all 50 nbrs
        cand_raw_mesh = get_cand_raw_mesh(cand_pmids, raw_data.nbr_tam)
        ## answers
        pos_meshList = list(set(std_raw_mesh)&set(cand_raw_mesh))
        neg_meshList = list(set(cand_raw_mesh)-set(pos_meshList))
        # if idx!=2:
        #     neg_meshList = random.sample(neg_meshList, len(pos_meshList)) # make a neg mesh subset 
        meshNum = len(pos_meshList)+len(neg_meshList) ## answer number for this PMID

        for p_mesh in pos_meshList:
            answer = rawMesh_meshAndEntry_dict.get(p_mesh) # answer may contain None
            if not answer: # if answer==None
                answer = [p_mesh] # answer is the pseudo mesh term itself
            answers.append(answer)
            qids.append(pmid)
            questions.append(clean_question)
            labels.append(1)

        for n_mesh in neg_meshList:
            answer = rawMesh_meshAndEntry_dict.get(n_mesh) ## clean mesh terms and entry terms
            if not answer: # if answer==None
                answer = [n_mesh] # answer is the pseudo mesh term itself            
            answers.append(answer) #  answer may contain None
            qids.append(pmid)
            questions.append(clean_question)
            labels.append(0)

    return qids, questions, answers, labels     

def compute_overlap_features(questions, answers, word2df=None, stoplist=None):
    '''the overlap percentage of tokens between evey pair of question and answer'''
    word2df = word2df if word2df else {}
    stoplist = stoplist if stoplist else set()
    feats_overlap = []
    for question, answer in zip(questions, answers):
        q_set = set([q for q in question if q not in stoplist])
        a_set = set([a for a in answer if a not in stoplist])
        word_overlap = q_set.intersection(a_set)
        overlap = float(len(word_overlap)) / (len(q_set) + len(a_set))
        df_overlap = 0.0
        for w in word_overlap:
            df_overlap += word2df[w]
        df_overlap /= (len(q_set) + len(a_set))

        feats_overlap.append(np.array([
                         overlap, ## normalized number of overlap tokens
                         df_overlap, ## normalized df of overlap tokens
                         ]))
    return np.array(feats_overlap)

def compute_overlap_idx(questions, answers, stoplist, q_max_sent_length, a_max_sent_length):
    stoplist = stoplist if stoplist else []
    feats_overlap = []
    q_indices, a_indices = [], []
    for question, answer in zip(questions, answers):
        # print "question"
        # print question[:100]
        # print
        # print "answer"
        # print answer
        # print
        q_set = set([q for q in question if q not in stoplist])
        a_set = set([a for a in answer if a not in stoplist])
        word_overlap = q_set.intersection(a_set)
        # print "word overlap"
        # print word_overlap
        # print
        # print "q_max_sent_length: ", q_max_sent_length
        # print
        q_idx = np.ones(q_max_sent_length) * 2
        # print "q_idx: ",q_idx.shape
        # print
        for i, q in enumerate(question):
            value = 0
            if q in word_overlap:
                value = 1
            q_idx[i] = value
        q_indices.append(q_idx)

        a_idx = np.ones(a_max_sent_length) * 2
        for i, a in enumerate(answer):
            value = 0
            if a in word_overlap:
                value = 1
            a_idx[i] = value
        a_indices.append(a_idx)

    q_indices = np.vstack(q_indices).astype('int32')
    a_indices = np.vstack(a_indices).astype('int32')
    # print "q_indices: ",q_indices.shape
    # print "a_indices: ", a_indices.shape
    return q_indices, a_indices

def compute_dfs(docs):
    '''compute document frequencies. not inversed df '''
    word2df = defaultdict(float)
    for doc in docs:
        if not doc: # if the doc is None
            continue        
        for w in set(doc):
            word2df[w] += 1.0
    num_docs = len(docs)
    for w, value in word2df.iteritems():
        word2df[w] /= np.math.log(num_docs / value)
    return word2df

def add_to_vocab(data, alphabet):
  for sentence in data:
    for token in sentence:
      alphabet.add(token)

def convert2indices(data, alphabet, dummy_word_idx, max_sent_length=40):
  data_idx = []
  for sentence in data:
    ex = np.ones(max_sent_length) * dummy_word_idx
    for i, token in enumerate(sentence):
      idx = alphabet.get(token, UNKNOWN_WORD_IDX)
      ex[i] = idx
    data_idx.append(ex)
  data_idx = np.array(data_idx).astype('int32')
  return data_idx

if __name__ == '__main__':
    stoplist = None
    '''
    Input dataformat: MEDLINE records. Include title, abstract, MeSH terms, entry terms, print entry terms, etc.
    Parser extracts these entities.
    title and abstract --> query
    mesh, entry, print entry --> document
    '''
    ## for idash-meta-dev
    # data_dir = "/home/w2wei/Research/mesh/data/deep_pmcoa/pointwise_ltr/sample/raw"
    ## for idash-cloud
    # data_dir = "/home/w2wei/projects/pointwiseLTR/data/sample"
    ## data are available from Lu_data L1000, N2007, and S200

    ## raw data preparation: prepare three files, train, dev and test. ready to use. the remaining code just need files names
    data_dir = "/home/w2wei/projects/pointwiseLTR/data/knn_sample"
    raw_data_dir = os.path.join(data_dir, "raw_data")    
    train_dir = os.path.join(raw_data_dir, "L1000")
    dev_dir = os.path.join(raw_data_dir, "NLM2007")
    test_dir = os.path.join(raw_data_dir, "SMALL200")
    clean_data_dir = os.path.join(data_dir, "clean_data")
    ## pre-process the raw data to generate data objects 
    raw_train = Data(raw_data_dir, clean_data_dir)
    raw_train.large1000()
    raw_dev = Data(raw_data_dir, clean_data_dir)    
    raw_dev.small200()
    raw_test = Data(raw_data_dir, clean_data_dir)    
    raw_test.nlm2007()

    outdir = os.path.join(data_dir, "Exp_7")#'{}'.format(name.upper())
    if not os.path.exists(outdir):
        os.makedirs(outdir)

    t0=time.time()
    qids, questions, answers, labels = load_all_data(raw_train, raw_dev, raw_test, stoplist) ## load data from sample_merged
    t1=time.time()
    print "Load all datasets: ",t1-t0 # 55 secs for 817 documents, 22689 answers
    print "qids: ", len(qids), len(set(qids))
    print
    ### Compute document frequencies.
    seen = set() ## set of unique qids
    unique_questions = [] ## list of unique questions
    for q, qid in zip(questions, qids):
      if qid not in seen:
        seen.add(qid)
        unique_questions.append(q)

    docs = answers + unique_questions ## a list of lists # None exists in docs

    word2dfs = compute_dfs(docs) ## idf of every word
    #########

    alphabet = Alphabet(start_feature_id=0) ## a dictionary {token: token index}
    alphabet.add('UNKNOWN_WORD_IDX')

    add_to_vocab(answers, alphabet)
    add_to_vocab(questions, alphabet)

    cPickle.dump(alphabet, open(os.path.join(outdir, 'vocab.pickle'), 'w'))

    dummy_word_idx = alphabet.fid

    q_max_sent_length = max(map(lambda x: len(x), questions))
    a_max_sent_length = max(map(lambda x: len(x), answers))
    print 'q_max_sent_length', q_max_sent_length
    print 'a_max_sent_length', a_max_sent_length

    # Convert dev and test sets
    # for fname in [train, dev, test]: ## extract additional features from all datasets
    obj_list = [raw_train, raw_dev, raw_test]
    name_list = ['train','dev','test']

    for i in range(len(obj_list)):
        qids, questions, answers, labels = load_data(obj_list[i], stoplist, i)
        print "dataset: ", name_list[i]
        print len(qids), len(set(qids))
        overlap_feats = compute_overlap_features(questions, answers, stoplist=None, word2df=word2dfs)
        overlap_feats_stoplist = compute_overlap_features(questions, answers, stoplist=stoplist, word2df=word2dfs)
        overlap_feats = np.hstack([overlap_feats, overlap_feats_stoplist])

        qids = np.array(qids)
        labels = np.array(labels).astype('int32')

        _, counts = np.unique(labels, return_counts=True) ## counts of unique components in label array

        # stoplist = None
        q_overlap_indices, a_overlap_indices = compute_overlap_idx(questions, answers, stoplist, q_max_sent_length, a_max_sent_length)
        # raw_input("....")

        questions_idx = convert2indices(questions, alphabet, dummy_word_idx, q_max_sent_length)
        answers_idx = convert2indices(answers, alphabet, dummy_word_idx, a_max_sent_length)

        # basename, _ = os.path.splitext(os.path.basename(fname))
        basename = name_list[i]
        # print basename
        # print "basename ", basename
        # print os.path.join(outdir, '{}.qids.npy'.format(basename))
        # print qids.shape
        # print os.path.join(outdir, '{}.questions.npy'.format(basename))
        # print questions_idx.shape
        # print os.path.join(outdir, '{}.answers.npy'.format(basename))
        # print answers_idx.shape
        # print os.path.join(outdir, '{}.labels.npy'.format(basename))
        # print labels.shape
        # print os.path.join(outdir, '{}.overlap_feats.npy'.format(basename))
        # print overlap_feats.shape
        # print os.path.join(outdir, '{}.q_overlap_indices.npy'.format(basename))
        # print q_overlap_indices.shape
        # print os.path.join(outdir, '{}.a_overlap_indices.npy'.format(basename))
        # print a_overlap_indices.shape
        # # raw_input("wait...")

        print "saving data..."
        np.save(os.path.join(outdir, '{}.qids.npy'.format(basename)), qids)
        np.save(os.path.join(outdir, '{}.questions.npy'.format(basename)), questions_idx)
        np.save(os.path.join(outdir, '{}.answers.npy'.format(basename)), answers_idx)
        np.save(os.path.join(outdir, '{}.labels.npy'.format(basename)), labels)
        np.save(os.path.join(outdir, '{}.overlap_feats.npy'.format(basename)), overlap_feats)

        np.save(os.path.join(outdir, '{}.q_overlap_indices.npy'.format(basename)), q_overlap_indices)
        np.save(os.path.join(outdir, '{}.a_overlap_indices.npy'.format(basename)), a_overlap_indices)
