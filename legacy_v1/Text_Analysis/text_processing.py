# -*- coding: UTF-8 -*- 
"""
Created on Fri Feb 23 12:37:46 2018

@author: Damon Li
"""

import numpy as np

import jieba, os
from gensim import corpora,similarities,models,matutils,utils


class TextProcessing(object):
    '''Text pre-processing functions class.

    # Arguments
        chnSTWPath: chinese stop words txt file path.
        finance_dict: latest financial related words txt file path.
    '''

    def __init__(self,chnSTWPath,finance_dict):
        self.chnSTWPath = chnSTWPath
        self.finance_dict = finance_dict

    def renewFinanceDict(self,new_Word_list):
        '''Add latest necessary financial words into financial dictionary
            for improving tokenization effect.

        # Arguments:
            new_Word_list: New financial words list, eg: ["区块链"，"离岸金融"].
        '''
        with open(self.finance_dict,'a',encoding='utf-8') as file:
            for word in new_Word_list:
                file.write(word + '\n')

    def getchnSTW(self):
        '''Load the stop words txt file.
        '''   
        stopwords = [line.strip() for line in open(self.chnSTWPath, 'r').readlines()]  
        return stopwords

    def jieba_tokenize(self,documents): 
        '''Cut the documents into a sequence of independent words.

        # Arguments:
            documents: List of news(articles).
        '''
        chnSTW = self.getchnSTW()
        corpora_documents = []
        jieba.load_userdict(self.finance_dict)
        for item_text in documents: 
            outstr = []
            sentence_seged = list(jieba.cut(item_text))
            for word in sentence_seged:  
                if word not in chnSTW and word != '\t' \
                and word != ' ':  
                    outstr.append(word)
            corpora_documents.append(outstr)
        return corpora_documents

    def RemoveWordAppearOnce(self,corpora_documents):
        '''Remove the words that appear once among all the tokenized news(articles).

        # Arguments:
             corpora_documents: List of tokenized news(articles).
        '''
        frequency = defaultdict(int)  
        for text in corpora_documents:  
            for token in text:      
                frequency[token] += 1 
        corpora_documents = [[token for token in text if frequency[token] > 1]  for text in corpora_documents] 
        return corpora_documents

    def genDictionary(self,documents,**kwarg):
        '''Generate dictionary and bow-vector of all tokenzied news(articles).

        # Arguments:
            documents: List of news(articles).
            saveDict: Save dictionary or not(bool type).
            saveBowvec: Save bow-vector or not(bool type).
            returnValue: Return value or not(bool type).
        '''
        self._raw_documents = documents
        token = self.jieba_tokenize(documents) #jieba tokenize
        #corpora_documents = self.RemoveWordAppearOnce(token)  # remove thw words appearing once in the dictionary
        self._dictionary = corpora.Dictionary(token)  # generate dictionary using tokenized documents  
        if kwarg['saveDict']:
            self._dictionary.save(kwarg['saveDictPath']) # store the dictionary, for future reference
        self._BowVecOfEachDoc = [self._dictionary.doc2bow(text) for text in token]  # convert tokenized documents to vectors
        if kwarg['saveBowvec']:
            corpora.MmCorpus.serialize(kwarg['saveBowvecPath'], self._BowVecOfEachDoc)  # store to disk, for later use
        if kwarg['returnValue']:
            return token, self._dictionary, self._BowVecOfEachDoc

    def CallTransformationModel(self,Dict,Bowvec,**kwarg):
        '''Invoke specific transformation models of Gensim module.

        # Arguments:
            Dict: Dictionary made by all tokenized news(articles/documents).
            Bowvec: Bow-vector created by all tokenized news(articles/documents).
            modelType: Transformation model type, including 'lsi', 'lda' and 'None', 'None' means TF-IDF mmodel.
            tfDim: The number of topics that will be extracted from each news(articles/documents). 
            renewModel: Re-train the transformation models or not(bool type).
            modelPath: The path of saving trained transformation models.
        '''
        if kwarg['renewModel']:
            tfidf = models.TfidfModel(Bowvec)  # initialize tfidf model
            tfidfVec = tfidf[Bowvec] # use the model to transform whole corpus
            tfidf.save(kwarg['modelPath']+"tfidf_model.tfidf")
            if kwarg['modelType'] == 'lsi':
                model = models.LsiModel(tfidfVec, id2word=Dict, num_topics=kwarg['tfDim']) # initialize an LSI transformation
                modelVec = model[tfidfVec] # create a double wrapper over the original corpus: bow->tfidf->fold-in-lsi
                model.save(kwarg['modelPath']) # same for tfidf, lda, ...
            elif kwarg['modelType'] == 'lda':
                model = models.LdaModel(tfidfVec, id2word=Dict, num_topics=kwarg['tfDim'])
                modelVec = model[tfidfVec] #每个文本对应的LDA向量，稀疏的，元素值是隶属与对应序数类的权重 
                model.save(kwarg['modelPath']) # same for tfidf, lda, ...
            elif kwarg['modelType'] == 'None': 
                model = tfidf
                modelVec = tfidfVec
        else:
            if not os.path.exists(kwarg['modelPath']+"tfidf_model.tfidf"):
                tfidf = models.TfidfModel(Bowvec)  # initialize tfidf model
                tfidfVec = tfidf[Bowvec] #
                tfidf.save(kwarg['modelPath']+"tfidf_model.tfidf")
            else:
                tfidf = models.TfidfModel.load(kwarg['modelPath']+"tfidf_model.tfidf") 
                tfidfVec = tfidf[Bowvec] # use the model to transform whole corpus
            if kwarg['modelType'] == 'lsi':
                if not os.path.exists(kwarg['modelPath']+"lsi_model.lsi"):
                    tfidf = models.TfidfModel.load(kwarg['modelPath']+"tfidf_model.tfidf") 
                    tfidfVec = tfidf[Bowvec] # use the model to transform whole corpus
                    model = models.LsiModel(tfidfVec, id2word=Dict, num_topics=kwarg['tfDim']) # initialize an LSI transformation
                    modelVec = model[tfidfVec] # create a double wrapper over the original corpus: bow->tfidf->fold-in-lsi
                    model.save(kwarg['modelPath']+"lsi_model.lsi") # same for tfidf, lda, ...
                else:
                    model = models.LsiModel.load(kwarg['modelPath']+"lsi_model.lsi")
                    modelVec = model[tfidfVec] 
            elif kwarg['modelType'] == 'lda':
                if not os.path.exists(kwarg['modelPath']+"lda_model.lda"):
                    tfidf = models.TfidfModel.load(kwarg['modelPath']+"tfidf_model.tfidf") 
                    tfidfVec = tfidf[Bowvec] # use the model to transform whole corpus
                    model = models.LdaModel(tfidfVec, id2word=Dict, num_topics=kwarg['tfDim'])
                    modelVec = model[tfidfVec] #每个文本对应的LDA向量，稀疏的，元素值是隶属与对应序数类的权重 
                    model.save(kwarg['modelPath']+"lda_model.lda") # same for tfidf, lda, ...
                else:
                    model = models.LdaModel.load(kwarg['modelPath']+"lda_model.lda")
                    modelVec = model[tfidfVec] 
            elif kwarg['modelType'] == 'None': 
                model = tfidf
                modelVec = tfidfVec
        return tfidfVec, modelVec

    def CalSim(self,test_document,Type,best_num):
        '''Calculate similarities between test document wth all news(articles/documents).

        # Arguments:
            test_document: List of raw documents.
            Type: Models of calculating similarities.
            best_num: refer to 'num_best' parameter in Gensim module.
        '''
        if Type == 'Similarity-tfidf-index':
            tfidf = models.TfidfModel(self._BowVecOfEachDoc)  
            tfidfVec = tfidf[self._BowVecOfEachDoc]
            self._num_features = len(self._dictionary.token2id.keys())
            self._similarity = similarities.Similarity(Type, tfidfVec, \
                num_features=self._num_features,num_best=best_num)  
            test_cut_raw = list(jieba.cut(test_document))  
            test_BowVecOfEachDoc = self._dictionary.doc2bow(test_cut_raw) 
            self._test_BowVecOfEachDoc = tfidf[test_BowVecOfEachDoc]
        elif Type == 'Similarity-LSI-index':
            lsi_model = models.LsiModel(self._BowVecOfEachDoc)  
            corpus_lsi = lsi_model[self._BowVecOfEachDoc]
            self._num_features = len(self._dictionary.token2id.keys())
            self._similarity = similarities.Similarity(Type, corpus_lsi, \
                num_features=self._num_features,num_best=best_num)  
            test_cut_raw = list(jieba.cut(test_document))  
            test_BowVecOfEachDoc = self._dictionary.doc2bow(test_cut_raw) 
            self._test_BowVecOfEachDoc = lsi_model[test_BowVecOfEachDoc]
        self.Print_CalSim()
        IdLst = []
        SimRltLst = []
        SimTxLst = []
        for Id, Sim in self._similarity[self._test_BowVecOfEachDoc]:
            IdLst.append(Id)
            SimRltLst.append(Sim)
            SimTxLst.append(self._raw_documents[Id])
        return IdLst,SimTxLst,SimRltLst

    def PrintWorfCloud(self,documents,backgroundImgPath,fontPath):
        '''Print out the word cloud of all news(articles/documents).

        # Arguments:
            documents: Overall raw documents.
            backgroundImgPath: Background image path.
            fontPath: The path of windows fonts that used to create the word-cloud.
        '''
        from scipy.misc import imread
        import matplotlib.pyplot as plt
        from wordcloud import WordCloud
        corpora_documents = self.jieba_tokenize(documents) #分词
        for k in range(len(corpora_documents)):
            corpora_documents[k] = ' '.join(corpora_documents[k])
        corpora_documents = ' '.join(corpora_documents)
        color_mask = imread(backgroundImgPath) #"C:\\Users\\lenovo\\Desktop\\Text_Mining\\3.jpg"
        cloud = WordCloud(font_path=fontPath,mask=color_mask,background_color='white',\
                          max_words=2000,max_font_size=40) #"C:\\Windows\\Fonts\\simhei.ttf"
        word_cloud = cloud.generate(corpora_documents) 
        plt.imshow(word_cloud, interpolation='bilinear')
        plt.axis("off")

if __name__ == '__main__':
    tp = TextProcessing(os.getcwd() + '\\' + 'Chinese_Stop_Words.txt', \
    os.getcwd() + '\\' + 'finance_dict.txt')
    doc = ['中央、地方支持政策频出,煤炭行业站上了风口 券商研报浩如烟海，投资线索眼花缭乱，第一财经推出\
            《一财研选》产品，挖掘研报精华，每期梳理5条投资线索，便于您短时间内获取有价值的信息。专业团队\
            每周日至每周四晚8点准时“上新”，\
            助您投资顺利！1．中央、地方支持政策频出，这个行业站上了风口！（信达证券）近年来，利好住房租赁\
            市场发展的政策频频发布，顶层设计趋于完善。信达证券指出，2015年以来，住建部、国务院等机构相继出\
            台政策支持住房租赁市场发展，地方积极跟进，试点城市全部出台相关方案支持当地住房租赁市场发展。除\
            此之外，“租购同权”保障承租人享受公共服务的权益，稳定租赁关系，利好长租公寓发展。除政策利好长租\
            公寓外，需求的逐步释放对长租公寓市场形成支撑。信达证券研究发现，人口向核心一、二线城市流动趋势不\
            减，高房价刺激购房需求转向租房需求、首次置业年龄抬升、高校毕业生租房需求增加等因素将刺激长租公寓\
            需求进一步释放。总体而言，住房租赁市场容量逾万亿且具备区域性特征。2017年8月，国土资源部、住房和城\
            乡建设部联合印发《利用集体建设用地建设租赁住房试点方案》，选择13个试点城市推进利用集体建设用地建\
            设租赁住房，各地“只租不售”地块频出，彰显政府发展住房租赁市场决心。类REITs产品盘活租赁资产，解决\
            长租融资痛点，上述举措能够有效增加租赁住房供给。伴随政策利好，多主体纷纷进军住房租赁市场。信达证\
            券指出，截至目前，房企、房地产中介、专业租赁机构、连锁酒店、金融机构和互联网公司均已涉足住宅租赁市\
            场。其中，房企多采用自持物业的重资产运营方式，中介机构及其他公司多以轻资产运营方式为主，从房源获\
            取的角度看，集中与分散并行。信达证券指出，当前我国租赁住房的发展还处于初步阶段，多主体参与、多模式\
            并存。参与各方均凭借自身比较优势切入住房租赁领域。未来，房企、互联网公司、金融机构存在巨大的合作空间。\
            在市场细分的前提下，增值服务的提供将成为住房租赁市场发展的关键。信达证券推荐关注招商蛇口(21.100, \
            -1.43, -6.35%)（001979.SZ）、万科A(31.270, -1.48, -4.52%)（000002.SZ）、世联行(8.700, -0.87,\
             -9.09%)（002285.SZ）、昆百大A(7.510, -0.05, -0.66%)（000560.SZ）、天健集团(9.330, -0.56, -5.66%)\
            （000090.SZ）。2．煤炭库存创八年新低，缺煤升级，高煤价仍将持续（中银国际）截至1月30日，秦皇岛5500大\
            卡山西优混动力煤报755元，跳涨2%，再超预期，并创近6年新高，此轮上涨持续了10周时间，累计涨幅达13%。煤炭\
            行业是本栏重点追踪的行业板块，近期的大涨验证了此前选摘的多家研究机构的观点，今天我们再来看一下中银国际\
            对板块未来表现的分析观点。中银国际指出，六大电厂日耗量周均81万吨，环比增加9%，库存天数由13天下降至10.9天\
            ，为近8年新低，库存下降至899万吨，为近7年新低。缺煤情况非常突出。经济的强韧性叠加寒冷冰雪天气推升需求超预\
            期是主因，供应侧在年关生产积极性不高、运输不畅是辅因，且短期较难明显缓解，2月初地方矿也面临陆续放假，在\
            这种情况下煤价有继续攀高的可能。中银国际认为此轮煤价上涨包含着较多非季节性因素：六大电厂日耗从2017年12月\
            开始同比增幅都在10%以上，这还是在有工业限产的情况下，这是非常高的数字，在2017年7~8月旺季的同比增幅也只\
            有15%左右。经济较好下的需求超预期历来是煤炭股最好的催化剂。尽管2月份由于春节因素可能价格会回落，但在2018\
            年缺煤明显的情况下，幅度不会太大，高煤价还会继续维持。3月初两会召开，安全形势再度紧张，煤炭的供应仍然会偏\
            紧，在叠加3月15日后限产解除，限产解除前后下游补库存，高煤价可能会贯穿整个一季度。中银国际指出，2017年1月秦\
            皇岛煤价均价只有602元，2018年1月的均价为726元，同比增长21%，动力煤公司一季度的业绩大概率会上调。尽管后续煤\
            价调控的压力在加大，但近期效果可能不明显，中期有待观察。煤炭板块2018年市盈率15倍，估值不贵，且存在继续上调\
            盈利预测和估值下行的可能，股价仍有空间。继续推荐动力煤龙头陕西煤业(8.340, -0.77, -8.45%)（601225.SH）、\
            兖州煤业(15.150, -1.24, -7.57%)（600803.SH）、中国神华(24.290, -1.16, -4.56%)（601088.SH），以及优质\
            的国企改革兼并重组题材股潞安环能(11.590, -1.11, -8.74%)（601699.SH）、山西焦化(12.420, -1.38, -10.00%\
            )（600740.SH）、山煤国际(4.520, -0.50, -9.96%)（600546.SH）、阳泉煤业(7.780, -0.86, -9.95%)（600348.SH）\
            。',\
            '郭文仓到重点工程项目督导检查 2月2日,公司党委书记、董事长、总经理郭文仓,公司董事,股份公司副总经理、总工程师、\
            郭毅民,股份公司副总经理张国富、柴高贵及相关单位负责人到焦化厂煤场全封闭和1#—4#干熄焦等重点工程项目建设工地\
            督导检查施工进度和安全工作情况。郭文仓一行实地查看并详细了解了现场施工情况,询问了施工队伍人员状况,他说,\
            煤场全封闭项目和1#—4#干熄焦项目是公司的重点环保项目,一定要力争将重点工程项目建成精品工程、一流环保标杆项目\
            。近日天气寒冷,又临近春节,煤场全封闭项目进入收尾的关键阶段,施工负责人要紧绷安全弦,加强现场安全管理,从细节抓\
            起,消除隐患,确保收尾工作安全稳定顺利。1#—4#干熄焦项目在大面积开工的重要时期,一定要统筹安排项目进度和质量\
            管理,落实好冬季防护措施,管控好每一道施工环节,目前尤其要注重人员的思想状况,做到不安全不施工,保证施工安全和人\
            员人身安全,确保项目“安全无事故、质量全达标、进度按计划、投资不超概、投产即达效、竣工不留尾、审计无问题、廉政建\
            设好”,为公司打造成全国独立焦化旗舰企业奠定坚实的基础。']
    DictPath = os.getcwd() + '\\' + 'stock_dict_file'
    stockCode = '600740'
    print(DictPath)
    print(DictPath+'\\'+stockCode+'\\'+stockCode+'_dict.dict')
    print(DictPath+'\\'+stockCode+'\\'+stockCode+'_bowvec.mm')
    if not os.path.exists(DictPath+'\\'+stockCode):
        os.makedirs(DictPath+'\\'+stockCode)
    tp.genDictionary(doc,saveDict=True,saveDictPath=DictPath+'\\'+stockCode+'\\'+stockCode+'_dict.dict',\
        saveBowvec=True,saveBowvecPath=DictPath+'\\'+stockCode+'\\'+stockCode+'_bowvec.mm',returnValue=False)