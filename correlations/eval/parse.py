#!/usr/bin/env python
# file created 5/1/2013

__author__ = "Will Van Treuren"
__copyright__ = "Copyright 2013, Will Van Treuren"
__credits__ = ["Will Van Treuren, Sophie Weiss"]
__license__ = "GPL"
__url__ = ''
__version__ = ".9-Dev"
__maintainer__ = "Will Van Treuren"
__email__ = "wdwvt1@gmail.com"


import re
from operator import itemgetter 
from numpy import (array, bincount, arange, histogram, corrcoef, triu_indices,
    where, vstack, logical_xor, searchsorted, zeros, linspace, tril, ones,
    repeat, empty, floor, ceil, hstack, tril_indices, inf, unique, isnan, triu)
from numpy.ma import masked_array as ma
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from biom.parse import parse_biom_table
from correlations.generators.ga import fitness
from matplotlib.pylab import matshow
from numpy.ma import masked_array
from linecache import getline

"""
Contains code for parsing outputs generated by SparCC, CoNet, RMT, and LSA.
The base class in this library is CorrelationCalcs. This class makes available 
all the simple calculations that we want to do for every result class so we can
easily parse and evaluate the results of the tools on a given data set. 

There are thus four derived classes: CoNetResults, SparCCResults, RMTResults, 
and LSAResults. Each of these classes does the parsing of the input lines and
implements any specific methods for the given tool.
"""

class CorrelationCalcs(object):
    '''Base class for correlation calculations performed for all methods.'''

    def connectionFraction(self, total_otus):
        '''Return: significant edges/all possible edges.'''
        return len(self.edges)/(total_otus*(total_otus-1.)/2.)

    def copresences(self):
        '''Return: number of copresences'''
        return self.interactions.count('copresence')

    def exclusions(self):
        '''Return: number of mutualExclusions'''
        return self.interactions.count('mutualExclusion')

    def connectionAbundance(self):
        '''Return data for a connection abundance graph'''
        nodes = self.sig_otus
        return bincount([self.otu1.count(i)+self.otu2.count(i) for i in nodes])

    def avgConnectivity(self):
        '''Return average number of connections of nodes'''
        # are we double counting here since edges = 2 x nodes?
        ca = self.connectionAbundance()
        return (ca*arange(len(ca))).sum()/ca.sum().astype(float) #avoid int div

    def otuConnectivity(self):
        '''Return list of (otu, connections it has) ordered by connections.'''
        nodes = self.sig_otus
        # edges can be o1--o5 or o5--o1, so look through both otu lists
        tmp = [(i,self.otu1.count(i)+self.otu2.count(i)) for i in nodes]
        return sorted(tmp, key=itemgetter(1), reverse=True)


class CoNetResults(CorrelationCalcs):
    '''Derived class CoNetResults handles parsing and specific functions.'''
    
    def __init__(self, lines):
        '''Initialize the object by parsing input file lines.

        Overall we create a single matrix nxm (n=number of edges, m=number of 
        metrics) where each row is an edge (i.e. otu1 -- otu4) and each column 
        is one of the metrics scores. The metrics are sorted in alphabetical 
        order in the parsed output, but they are given in a different order for
        each edge in the input.

        Ex: 
                      m1  m2  m3  m4
        otu1-otu4   [1.3, 4.6, 0.0, 0.6]
        otu13-otu38 [6.7, -1.2, 9.8, -0.5]
        '''
        
        vals = [line.split('\t') for line in lines]
        if len(vals) == 1:
            self._hackish_empty_results_fix()
        else:
            data = [[],[],[],[],[],[],[]]
            for line in vals[1:]: #skip the header line
                [data[ind].append(val) for ind,val in enumerate(line)]

            self.otu1 = list(data[0])
            self.otu2 = list(data[1])
            self.sig_otus = list(set(self.otu1+self.otu2))
            self.edges = zip(self.otu1, self.otu2)
            self.interactions = data[2]
            self.pvals = map(float,data[4])
            self.qvals = map(float,data[5])
            self.cvals = map(lambda x: 1.0 if x=='copresence' else -1.0, 
                             self.interactions)
            self.sigs = map(float,data[6])
     
            # method scores are given in a different order for each edge. 
            # method names are of the form abc_def. 
            sorted_methods = sorted(re.findall('[a-zA-Z]+_?[a-zA-Z]+',data[3][0]))
            sorted_scores = []
            for m_s_str in data[3]:
                methods = re.findall('[a-zA-Z]+_?[a-zA-Z]+', m_s_str)
                scores = re.findall('-?[0-9]+?\.[0-9]+', m_s_str)
                tmp = sorted(zip(methods,scores), key=itemgetter(0))
                sc = [float(score) for method,score in tmp]
                sorted_scores.append(sc)
            # WARNING: if any scores are of the form .351 with no preceeding 0, the
            # code will fail to capture this value.
            self.scores = array(sorted_scores).astype(float)
            self.methods = sorted_methods

    def methodVals(self, method):
        '''Return vectors of values for passed method.'''
        try:
            return self.scores[:,self.methods.index(method)]
        except ValueError:
            print 'Passed method not in methods. Methods are:\n%s' % \
                ('\n'.join(self.methods))

    def _hackish_empty_results_fix(self):
        '''This sets important properties to 0's, []'s, etc if no results.'''
        self.otu1 = []
        self.otu2 = []
        self.sig_otus = []
        self.edges = []
        self.interactions = []
        self.pvals = []
        self.qvals = []
        self.sigs = []


class RMTResults(CorrelationCalcs):
    '''Derived class RMTResults handles parsing and specific functions.'''

    def __init__(self, lines):
        '''Initialize the objectby parsing input file lines.'''
        
        vals = [line.split('\t') for line in lines]
        data = [[],[],[],[],[]]
        for line in vals[1:]: #skip the header line
            [data[ind].append(val) for ind,val in enumerate(line)]
        # set easy properties
        self.otu1 = list(data[0])
        self.otu2 = list(data[1])
        self.sig_otus = list(set(self.otu1+self.otu2))
        self.edges = zip(self.otu1, self.otu2)
        # Pearson score is utilized to compare these OTUs so all will have an 
        # interaction='Correlated'. Things with a negative correlation score
        # are negative interactions, so we can assign the interaction ourselves.
        self.scores = map(float,data[3])
        self.cvals = self.scores
        interactions = []
        for i in self.scores:
            if i>=0:
                interactions.append('copresence')
            elif i<0:
                interactions.append('mutualExclusion')
        self.interactions =  interactions

        # find significance
        sig_vals = []
        for sig in data[4]:
            sig_val = re.findall('-?[0-9]+?\.[0-9]+',sig)
            sig_vals.append(float(sig_val[0]))
        self.sigs = sig_vals


class SparCCResults(CorrelationCalcs):
    '''Derived class SparCCResults handles parsing and specific functions.'''

    def __init__(self, pval_lines, corr_lines, sig_lvl=.05,
                 pearson_filter=None):
        '''Initialize self by parsing input lines.

        Structure of this init is slightly different than the others because we
        might want to change the significance level from .05.

        Unlike the other parsers, SparCC seeks to estimate the linear 
        correlation only, and thus we need to provide a significance level to 
        decide which are significant. The pval_lines encode the fraction of 
        times a pvalue as extreme was seen in the bootstrapping trials SparCC 
        conducted as the one calculated from the estimated linear correlation 
        encoded in corr_lines.
        '''
        vals = array([line.strip().split('\t') for line in pval_lines])
        self.data = vals[1:,1:].astype(float) #avoid row,col headers
        self.otu_ids = vals[0,1:]
        cvals = array([line.strip().split('\t') for line in corr_lines])
        self.cdata = cvals[1:,1:].astype(float) #avoid row,col headers
        self._getSignificantData(sig_lvl, pearson_filter)
        self._getLPSAndInteractions()

    def _getSignificantData(self, sig_lvl, pearson_filter):
        '''Find which edges significant at passed level and set self properties.
        '''
        # correlation metrics are symmetric: adjust values of lower triangle  
        # be larger than sig_lvl means only upper triangle values get chosen.
        # data is nxn matrix
        rows,cols = self.data.shape
        if pearson_filter is not None:
            # find edges which are significant enough based on sig_lvl
            se = (tril(10*ones((rows, cols)),0)+self.data)<=sig_lvl
            # find edges which are significant enough based on pearson_filter
            pe = abs(triu(self.cdata, 1))>=pearson_filter
            self.sig_edges = (se * pe).nonzero()
        else: 
            # sig edges is tuple of arrays corresponding to row,col indices
            self.sig_edges = \
                ((tril(10*ones((rows, cols)),0)+self.data)<=sig_lvl).nonzero()
        self.otu1 = [self.otu_ids[i] for i in self.sig_edges[0]]
        self.otu2 = [self.otu_ids[i] for i in self.sig_edges[1]]
        self.sig_otus = list(set(self.otu1+self.otu2))
        self.edges = zip(self.otu1, self.otu2)
        self.pvals = \
            [self.data[i][j] for i,j in zip(self.sig_edges[0],self.sig_edges[1])]

    def _getLPSAndInteractions(self):
        '''Find linearized pearson scores given current significant edges.'''
        self.cvals = \
            [self.cdata[i][j] for i,j in zip(self.sig_edges[0],self.sig_edges[1])]
        interactions = []
        for i in self.cvals:
            if i>=0:
                interactions.append('copresence')
            elif i<0:
                interactions.append('mutualExclusion')
        self.interactions =  interactions

    def changeSignificance(self, sig_lvl):
        '''Recalculate all self properties at a new significance level.'''
        self._getSignificantData(sig_lvl)
        self._getLPSAndInteractions()


def triu_from_flattened(n, offset=0):
    '''Yield indices in flattened vector which construct upper triangular array.

    This function returns the indices in a flattened vector that would be needed
    to construct the upper triangular portion of a nXn array with given 
    offset (0 offset excludes main diagonal, positive offset moves exclusion up, 
    negative moves exclusion down).
    '''
    return (i for i in xrange(1, n**2+1) if i%n > offset+i/n)


class LSAResults(CorrelationCalcs):
    '''Derived class LSAResults handles parsing and specific functions.'''

    def __init__(self, lines, filter, sig_lvl, rtype='unique'):
        '''Initialize self by parsing inputs lines.

        The parsing for LSA has to be done carefully because the output tables 
        are much larger than for the other tools, due to the number of different
        calculations LSA records, and because the table LSA outputs contains 
        every possible edge in the table (including oX-oX, oY-oX and oX-oY even
        though relations are symmetric).

        Data matrix that is constructed by this function is kX10 matrix where 
        the cols correspond to:
        [0,1] LS score, LS p-val, 
        [2,3] Global Pearson score, Global Pearson p-val
        [4,5] Shifted Pearson score, Shifted Pearson p-val
        [6,7] Global Spearman score, Global Spearman p-val
        [8,9] Shifted Spearman score, Shifted Spearman p-val

        Inputs:
         lines - list of strs, lines of the LSA output. 
         filter - str, one of 'ls', 'ss', 'sp', 'gs', 'gp' which determines 
         which value to use for filtration. 
         sig_lvl - float, value to use as the score for filtering out non-sig
         edges.
         rtype - str, either 'redundant' or 'unique'. 'redundant' indicates that
         the lines in the output file have both ox, oy and oy, ox. that means 
         the file is n**2 lines long (n is num otus). if 'unique' file only 
         has ox,oy and num lines is n(n-1)/2.
        '''
        # set up properties we need later
        data = []
        self.otu1 = []
        self.otu2 = []
        self.pvals = []
        self.interactions = []
        self.scores = []
        self.cvals = self.scores

        # filter_by_map indicates which column index in the input file 
        # corresponds to which method p-value for a given edge. 
        # value_filter_map tells where the corresponding score of the method is
        # i.e. tmp[9] is the pval for the ls score, and tmp[2] is the actual 
        # score
        filter_map = {'ls': 9, 'ss': 18, 'sp': 13, 'gs': 16, 'gp': 11}
        value_filter_map = {'ls': 2, 'ss': 17, 'sp': 12, 'gs': 15, 'gp': 10}
        try: 
            self.filter_ind = filter_map[filter]
            self.value_filter_ind = value_filter_map[filter]
        except KeyError:
            raise ValueError('Must filter by one of:\n%s' % \
                (', '.join(filter_map.keys())))

        # loi is generator of indices of lines of interest. we are assuming that
        # lines consists of one header line and then data lines
        num_otus = int((len(lines)-1)**.5)
        if rtype=='autodetect':
            tmp = lines[1].split('\t')
            if tmp[0] == tmp[1]:
                rtype = 'redundant'
            elif tmp[0] != tmp[1]:
                rtype = 'unique'
            else:
                raise ValueError('Unknown input type.')
        if rtype=='redundant':
            loi = triu_from_flattened(num_otus,offset=0)
        elif rtype=='unique':
            loi = range(0,len(lines)-1)
        for i in loi:
            tmp = lines[i+1].strip().split('\t')
            if self._isSignificant(tmp, self.filter_ind, sig_lvl):
                vals = [tmp[2], tmp[9], tmp[10], tmp[11], tmp[12], tmp[13],
                    tmp[15], tmp[16], tmp[17], tmp[18]]
                data.append(map(float, vals))
                self.otu1.append(tmp[0])
                self.otu2.append(tmp[1])
                self.pvals.append(float(tmp[self.filter_ind]))
                self.scores.append(float(tmp[self.value_filter_ind]))
                # evaluate interactions since only score given
                if float(tmp[self.value_filter_ind]) >= 0:
                    self.interactions.append('copresence')
                else:
                    self.interactions.append('mutualExclusion')
            else:
                pass

        self.edges = zip(self.otu1, self.otu2)
        self.data = array(data)
        self.sig_otus = list(set(self.otu1).union(self.otu2))

    def _isSignificant(self, line, ind, sig_lvl):
        '''Return true if line has significant value in given index.'''
        return True if float(line[ind]) < sig_lvl else False

    def getMethodData(self, data_index):
        '''Look at class documentation to figure out which index you want.
        '''
        return self.data[:, data_index]


class NaiveResults(CorrelationCalcs):
    '''Derived class handles calculations for naive correlation method.'''

    def __init__(self, cval_lines, pval_lines, sig_lvl, empirical=False):
        '''Init self by parsing cvals and calculating sig links.'''
        vals = array([line.strip().split('\t') for line in pval_lines])
        self.pdata = vals[1:,1:].astype(float) #avoid row,col headers
        # nan pdata gets a pvalue of 1.
        nan_indicies = isnan(self.pdata)
        self.pdata[nan_indicies] = 1
        self.otu_ids = vals[0,1:]
        cvals = array([line.strip().split('\t') for line in cval_lines])
        self.cdata = cvals[1:,1:].astype(float) #avoid row,col headers
        # nan correlated data gets cval of 0.
        self.cdata[nan_indicies] = 0.
        self._getSignificantData(sig_lvl, empirical)
        self._getLPSAndInteractions()

    def _getSignificantData(self, sig_lvl, empirical):
        '''Find which edges significant at passed level and set self properties.
        '''
        rows,cols = self.pdata.shape #rows = cols
        if empirical:
            mask = zeros((rows,cols))
            mask[tril_indices(rows,0)] = 1 #preparing mask
            # cvals = list(set(self.cdata[triu_indices(rows,-1)]))
            # cvals.sort()
            cvals = unique(self.cdata[triu_indices(rows,1)])
            alpha = sig_lvl/2.
            lb = round(cvals[floor(alpha*len(cvals))],7)
            ub = round(cvals[-ceil(alpha*len(cvals))],7)
            if sig_lvl==0.:
                lb = -inf
                ub = inf
            mdata = ma(self.cdata, mask)
            if lb==ub:
                # overcount is going to happen 
                print 'lb, ub: %s %s' % (lb, ub), (mdata>=ub).sum(), (mdata<=lb).sum(), (mdata==lb).sum(), (mdata==ub).sum(), lb==ub
            # because of the floor and ceil calculations we used >= for the 
            # upper and lower bound calculations. as an example, assume you have
            # 100 pvals, and are choosing sig_lvl=.05. Then you will pick 2.5 
            # values on each side. Since we don't know what the pvalue is for 
            # the 2.5th value in the list (it DNE), we round down to the 2nd 
            # 2nd value for the lower bound, and round up to the 98th value for
            # the upper bound.
            upper_sig_edges = where(mdata>=ub,1,0).nonzero()
            lower_sig_edges = where(mdata<=lb,1,0).nonzero()
            e1 = hstack([upper_sig_edges[0], lower_sig_edges[0]])
            e2 = hstack([upper_sig_edges[1], lower_sig_edges[1]])
            self.sig_edges = (e1,e2)
            self.otu1 = [self.otu_ids[i] for i in self.sig_edges[0]]
            self.otu2 = [self.otu_ids[i] for i in self.sig_edges[1]]
            self.sig_otus = list(set(self.otu1+self.otu2))
            self.edges = zip(self.otu1, self.otu2)
            self.pvals = [self.pdata[i][j] for i,j in zip(self.sig_edges[0],
                self.sig_edges[1])]
            #print sig_lvl, len(self.sig_edges[0]), self.cdata.shape, lb, ub, self.sig_edges[0][:10], self.sig_edges[1][:10]
            #print alpha, lb, ub, kfhf
        else:
            # correlation metrics are symmetric: adjust values of lower triangle  
            # to be larger than sig_lvl means only upper triangle values get 
            # chosen.
            # data is nxn matrix
            # sig edges is tuple of arrays corresponding to row,col indices
            tmp = (self.pdata <= sig_lvl)
            tmp[tril_indices(self.pdata.shape[0], 0)] = 0
            self.sig_edges = tmp.nonzero()
            self.otu1 = [self.otu_ids[i] for i in self.sig_edges[0]]
            self.otu2 = [self.otu_ids[i] for i in self.sig_edges[1]]
            self.sig_otus = list(set(self.otu1+self.otu2))
            self.edges = zip(self.otu1, self.otu2)
            self.pvals = [self.pdata[i][j] for i,j in zip(self.sig_edges[0],
                self.sig_edges[1])]
            #print sig_lvl, len(self.sig_edges[0]), self.cdata.shape, self.sig_edges[0][:10], self.sig_edges[1][:10]


    def _getLPSAndInteractions(self):
        '''Find linearized pearson scores given current significant edges.'''
        self.cvals = \
            [self.cdata[i][j] for i,j in zip(self.sig_edges[0],self.sig_edges[1])]
        interactions = []
        for i in self.cvals:
            if i>=0:
                interactions.append('copresence')
            elif i<0:
                interactions.append('mutualExclusion')
        self.interactions =  interactions

    def changeSignificance(self, sig_lvl, empirical):
        '''Recalculate all self properties at a new significance level.'''
        self._getSignificantData(sig_lvl, empirical)
        self._getLPSAndInteractions()


class BrayCurtisResults(CorrelationCalcs):
    '''Derived class handles calculations for bray curtis correlation method.

    Bray Curtis is different than the other methods in that it doesn't say if 
    a linkage is positive or negative (its a dissimilarity measure, not a 
    measure of correlation). This means we will take only values on the left 
    tail of the distribution.
    '''

    def __init__(self, dissim_lines, sig_lvl):
        '''Init self by parsing dissim_lines and calculating sig links.'''
        # error check at the beginning avoids computation
        if sig_lvl==0.:
            raise ValueError('sig_lvl cannot be 0. pass sig_lvl > 0.')
        # begin parsing
        vals = array([line.strip().split('\t') for line in dissim_lines])
        self.data = vals[1:,1:].astype(float) #avoid row,col headers
        self.otu_ids = vals[0,1:]
        self._getSignificantData(sig_lvl)
        # HACK
        # since there is no notion of mutual exclusion we have to assign our 
        # significant interactions as nothing
        #self.interactions = []
        self.interactions = ['copresence']* len(self.edges)
        if sig_lvl != self.actual_sig_lvl:
            print 'Warning: calculated sig_lvl is %s' % self.actual_sig_lvl

    def _getSignificantData(self, sig_lvl):
        '''Find which edges significant at passed level and set self properties.
        '''
        rows,cols = self.data.shape #rows = cols
        mask = zeros((rows,cols))
        mask[tril_indices(rows,0)] = 1 #preparing mask
        cvals = unique(self.data[triu_indices(rows,1)]) # cvals is sorted
        # calculate lower bound, i.e. what value in the distribution of values 
        # has sig_lvl fraction of the data lower than or equal to it. this is
        # not guaranteed to be precise because of repeated values. for instance 
        # assume the distribution of dissimilarity values is:
        # [.1, .2, .2, .2, .2, .3, .4, .5, .6, .6] 
        # and you want sig_lvl=.2, i.e. you get 20 percent of the linkages as 
        # significant. this would result in choosing the score .2 since its the
        # second in the ordered list (of 10 elements, 2/10=.2). but, since there
        # is no a-priori way to tell which of the multiple .2 linkages are 
        # significant, we select all of them, forcing our lower bound to 
        # encompass 50 percent of the data. the round call on the lb is to avoid
        # documented numpy weirdness where it will misassign >= calls for long
        # floats. 
        lb = round(cvals[round(sig_lvl*len(cvals))-1],7) #-1 because 0 indexing
        mdata = ma(self.data, mask)
        self.actual_sig_lvl = \
            (mdata <= lb).sum()/float(mdata.shape[0]*(mdata.shape[0]-1)/2)
        self.sig_edges = where(mdata <= lb, 1, 0).nonzero()
        self.otu1 = [self.otu_ids[i] for i in self.sig_edges[0]]
        self.otu2 = [self.otu_ids[i] for i in self.sig_edges[1]]
        self.sig_otus = list(set(self.otu1+self.otu2))
        self.edges = zip(self.otu1, self.otu2)
        self.cvals = mdata[self.sig_edges[0], self.sig_edges[1]]


class MICResults(CorrelationCalcs):
    """Derived class handles calculations for MIC correlation method."""

    def __init__(self, mic_lines, feature_names, sig_lvl):
        '''Init self by parsing mic lines and feature_names to get order.'''
        # error check at the beginning avoids computation
        if sig_lvl==0.:
            raise ValueError('sig_lvl cannot be 0. pass sig_lvl > 0.')
        # no feature identifiers so we can parse mic_lines directly to data
        self.data = array([map(float, line.strip().split(' ')) for line in 
            mic_lines])
        self.otu_ids = feature_names
        self._getSignificantData(sig_lvl)
        # HACK
        # since there is no notion of mutual exclusion we have to assign our 
        # significant interactions as nothing
        #self.interactions = []
        self.interactions = ['copresence']* len(self.edges)
        if sig_lvl != self.actual_sig_lvl:
            print 'Warning: calculated sig_lvl is %s' % self.actual_sig_lvl

    def _getSignificantData(self, sig_lvl):
        '''Find which edges significant at passed level and set self properties.
        '''
        rows,cols = self.data.shape #rows = cols
        mask = zeros((rows,cols))
        mask[tril_indices(rows,0)] = 1 #preparing mask
        cvals = unique(self.data[triu_indices(rows,1)]) # cvals is sorted
        # calculate upper bound, i.e. what value in the distribution of values 
        # has sig_lvl fraction of the data higher than or equal to it. this is
        # not guaranteed to be precise because of repeated values. for instance 
        # assume the distribution of dissimilarity values is:
        # [.1, .2, .2, .2, .2, .3, .4, .5, .6, .6, .6, .6, .6, .6, .7] 
        # and you want sig_lvl=.2, i.e. you get 20 percent of the linkages as 
        # significant. this would result in choosing the score .6 since its the
        # third in the ordered list (of 15 elements, 3/15=.2). but, since there
        # is no a-priori way to tell which of the multiple .6 linkages are 
        # significant, we select all of them, forcing our lower bound to 
        # encompass 7/15ths of the data. the round call on the ub is to avoid
        # documented numpy weirdness where it will misassign >= calls for long
        # floats. 
        ub = round(cvals[-round(sig_lvl*len(cvals))],7)
        mdata = ma(self.data, mask)
        self.actual_sig_lvl = \
            (mdata >= ub).sum()/float(mdata.shape[0]*(mdata.shape[0]-1)/2)
        self.sig_edges = where(mdata >= ub, 1, 0).nonzero()
        self.otu1 = [self.otu_ids[i] for i in self.sig_edges[0]]
        self.otu2 = [self.otu_ids[i] for i in self.sig_edges[1]]
        self.sig_otus = list(set(self.otu1+self.otu2))
        self.edges = zip(self.otu1, self.otu2)
        self.cvals = mdata[self.sig_edges[0], self.sig_edges[1]]
        

def sparcc_maker(cval_fp, pval_fp, sig_lvl=.001, pearson_filter=None):
    """convenience function, automate creation of sparcc object."""
    o = open(cval_fp)
    cval_lines = o.readlines()
    o.close()
    o = open(pval_fp)
    pval_lines = o.readlines()
    o.close()
    return SparCCResults(pval_lines, cval_lines, sig_lvl, pearson_filter)

def conet_maker(ensemble_fp):
    """convenience function, automate creation of conet object."""
    o = open(ensemble_fp, 'U')
    lines = o.readlines()
    o.close()
    return CoNetResults(lines)

def rmt_maker(results_fp):
    """convenience function, automate creation of rmt object."""
    o = open(results_fp, 'U')
    lines = o.readlines()
    o.close()
    return RMTResults(lines)

def lsa_maker(lsa_fp, filter_str='ls', sig_lvl=.001, rtype='autodetect'):
    """convenience function, automate creation of lsa object."""
    o = open(lsa_fp, 'U')
    lines = o.readlines()
    o.close()
    return LSAResults(lines, filter_str, sig_lvl, rtype=rtype)

def naive_maker(cval_fp, pval_fp, sig_lvl=.001):
    """convenience function, automate creation of naive object."""
    o = open(cval_fp, 'U')
    clines = o.readlines()
    o.close()
    o = open(pval_fp, 'U')
    plines = o.readlines()
    o.close()
    return NaiveResults(clines, plines, sig_lvl)

def bray_curtis_maker(dists_fp, sig_lvl=.001):
    """convenience function, automate creation of bray curtis object."""
    o = open(dists_fp, 'U')
    lines = o.readlines()
    o.close()
    return BrayCurtisResults(lines, sig_lvl)

def mic_maker(mic_fp, feature_names, sig_lvl=.3):
    """convenience function, automate creation of mic results object."""
    o = open(mic_fp, 'U')
    lines = o.readlines()
    o.close()
    return MICResults(lines, feature_names, sig_lvl)
