import __init__

import os
import time

from Kite import config
from Kite import utils
from Kite.database import Database
from Leorio.tokenization import Tokenization
from Hisoka.classifier import Classifier

from sklearn import preprocessing

from gensim import corpora
from gensim import models
from gensim.matutils import corpus2dense

import logging
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s",
                    datefmt="%a, %d %b %Y %H:%M:%S")


class TopicModelling(object):

    def __init__(self):
        self.tokenization = Tokenization(import_module="jieba",
                                         user_dict=config.USER_DEFINED_DICT_PATH,
                                         chn_stop_words_dir=config.CHN_STOP_WORDS_PATH)
        self.database = Database()
        self.classifier = Classifier()

    def create_dictionary(self,
                          raw_documents_list,
                          save_path=None,
                          is_saved=False):
        """
        将文中每个词汇关联唯一的ID，因此需要定义词汇表
        :param: raw_documents_list, 原始语料列表，每个元素即文本，如["洗尽铅华...", "风雨赶路人...", ...]
        :param: savepath, corpora.Dictionary对象保存路径
        """
        documents_token_list = []
        for doc in raw_documents_list:
            documents_token_list.append(self.tokenization.cut_words(doc))
        _dict = corpora.Dictionary(documents_token_list)
        # 找到只出现一次的token
        once_items = [_dict[tokenid] for tokenid, docfreq in _dict.dfs.items() if docfreq == 1]
        # 在documents_token_list的每一条语料中，删除只出现一次的token
        for _id, token_list in enumerate(documents_token_list):
            documents_token_list[_id] = list(filter(lambda token: token not in once_items, token_list))
        # 极端情况，某一篇语料所有token只出现一次，这样该篇新闻语料的token列表就变为空，因此删除掉
        documents_token_list = [token_list for token_list in documents_token_list if (len(token_list) != 0)]
        # 找到只出现一次的token对应的id
        once_ids = [tokenid for tokenid, docfreq in _dict.dfs.items() if docfreq == 1]
        # 删除仅出现一次的词
        _dict.filter_tokens(once_ids)
        # 消除id序列在删除词后产生的不连续的缺口
        _dict.compactify()
        if is_saved and save_path:
            _dict.save(save_path)
            logging.info("new generated dictionary saved in path -> {} ...".format(save_path))

        return _dict, documents_token_list

    def renew_dictionary(self,
                         old_dict_path,
                         new_raw_documents_list,
                         new_dict_path=None,
                         is_saved=False):
        documents_token_list = []
        for doc in new_raw_documents_list:
            documents_token_list.append(self.tokenization.cut_words(doc))
        _dict = corpora.Dictionary.load(old_dict_path)
        _dict.add_documents(documents_token_list)
        if new_dict_path:
            old_dict_path = new_dict_path
        if is_saved:
            _dict.save(old_dict_path)
            logging.info("updated dictionary by another raw documents serialized in {} ... ".format(old_dict_path))

        return _dict, documents_token_list

    def create_bag_of_word_representation(self,
                                          raw_documents_list,
                                          old_dict_path=None,
                                          new_dict_path=None,
                                          bow_vector_save_path=None,
                                          is_saved_dict=False):
        if old_dict_path:
            # 如果存在旧的语料词典，就在原先词典的基础上更新，增加未见过的词
            corpora_dictionary, documents_token_list = self.renew_dictionary(old_dict_path,
                                                                             raw_documents_list,
                                                                             new_dict_path=new_dict_path)
        else:
            # 否则重新创建词典
            start_time = time.time()
            corpora_dictionary, documents_token_list = self.create_dictionary(raw_documents_list,
                                                                              save_path=new_dict_path,
                                                                              is_saved=is_saved_dict)
            end_time = time.time()
            logging.info("there are {} mins spent to create a new dictionary ... ".format((end_time-start_time)/60))
        # 根据新词典对文档(或语料)生成对应的词袋向量
        start_time = time.time()
        bow_vector = [corpora_dictionary.doc2bow(doc_token) for doc_token in documents_token_list]
        end_time = time.time()
        logging.info("there are {} mins spent to calculate bow-vector ... ".format((end_time - start_time) / 60))
        if bow_vector_save_path:
            corpora.MmCorpus.serialize(bow_vector_save_path, bow_vector)

        return documents_token_list, corpora_dictionary, bow_vector

    @staticmethod
    def transform_vectorized_corpus(corpora_dictionary,
                                    bow_vector,
                                    model_type="lda",
                                    model_save_path=None):
        # 如何没有保存任何模型，重新训练的情况下，可以选择该函数
        model_vector = None
        if model_type == "lsi":
            # LSI(Latent Semantic Indexing)模型，将文本从词袋向量或者词频向量(更好)，转为一个低维度的latent空间
            # 对于现实语料，目标维度在200-500被认为是"黄金标准"
            model_tfidf = models.TfidfModel(bow_vector)
            # model_tfidf.save("model_tfidf.tfidf")
            tfidf_vector = model_tfidf[bow_vector]
            model = models.LsiModel(tfidf_vector,
                                    id2word=corpora_dictionary,
                                    num_topics=config.TOPIC_NUMBER)  # 初始化模型
            model_vector = model[tfidf_vector]
            if model_save_path:
                model.save(model_save_path)
        elif model_type == "lda":
            model = models.LdaModel(bow_vector,
                                    id2word=corpora_dictionary,
                                    num_topics=config.TOPIC_NUMBER)  # 初始化模型
            model_vector = model[bow_vector]
            if model_save_path:
                model.save(model_save_path)
        elif model_type == "tfidf":
            model = models.TfidfModel(bow_vector)  # 初始化
            # model = models.TfidfModel.load("model_tfidf.tfidf")
            model_vector = model[bow_vector]  # 将整个语料进行转换
            if model_save_path:
                model.save(model_save_path)

        return model_vector

    def classify_stock_news(self,
                            unseen_raw_document,
                            database_name,
                            collection_name,
                            label_name="60DaysLabel",
                            topic_model_type="lda",
                            classifier_model="svm",
                            ori_dict_path=None,
                            bowvec_save_path=None,
                            is_saved_bow_vector=False):
        historical_raw_documents_list = []
        Y = []
        for row in self.database.get_collection(database_name, collection_name).find():
            if label_name in row.keys():
                if row[label_name] != "":
                    historical_raw_documents_list.append(row["Article"])
                    Y.append(row[label_name])
        logging.info("fetch symbol '{}' historical news with label '{}' from [DB:'{}' - COL:'{}'] ... "
                     .format(collection_name, label_name, database_name, collection_name))

        le = preprocessing.LabelEncoder()
        Y = le.fit_transform(Y)
        logging.info("encode historical label list by sklearn preprocessing for training ... ")
        label_name_list = le.classes_  # ['中性' '利好' '利空'] -> [0, 1, 2]

        # 根据历史新闻数据库创建词典，以及计算每个历史新闻的词袋向量；如果历史数据库创建的字典存在，则加载进内存
        # 用未见过的新闻tokens去更新该词典
        if not os.path.exists(ori_dict_path):
            if not os.path.exists(bowvec_save_path):
                _, _, historical_bow_vec = self.create_bag_of_word_representation(historical_raw_documents_list,
                                                                                  new_dict_path=ori_dict_path,
                                                                                  bow_vector_save_path=bowvec_save_path,
                                                                                  is_saved_dict=True)
                logging.info("create dictionary of historical news, and serialized in path -> {} ... ".format(ori_dict_path))
                logging.info("create bow-vector of historical news, and serialized in path -> {} ... ".format(bowvec_save_path))
            else:
                _, _, _ = self.create_bag_of_word_representation(historical_raw_documents_list,
                                                                 new_dict_path=ori_dict_path,
                                                                 is_saved_dict=True)
                logging.info("create dictionary of historical news, and serialized in path -> {} ... ".format(ori_dict_path))
        else:
            if not os.path.exists(bowvec_save_path):
                _, _, historical_bow_vec = self.create_bag_of_word_representation(historical_raw_documents_list,
                                                                                  new_dict_path=ori_dict_path,
                                                                                  bow_vector_save_path=bowvec_save_path,
                                                                                  is_saved_dict=True)
                logging.info("historical news dictionary existed, which saved in path -> {}, but not the historical bow-vector"
                             " ... ".format(ori_dict_path))
            else:
                historical_bow_vec_mmcorpus = corpora.MmCorpus(bowvec_save_path)  # type -> <gensim.corpora.mmcorpus.MmCorpus>
                historical_bow_vec = []
                for _bow in historical_bow_vec_mmcorpus:
                    historical_bow_vec.append(_bow)
                logging.info("both historical news dictionary and bow-vector existed, load historical bow-vector to memory ... ")

        start_time = time.time()
        updated_dictionary_with_old_and_unseen_news, unssen_documents_token_list = self.renew_dictionary(ori_dict_path,
                                                                                                         [unseen_raw_document],
                                                                                                         is_saved=True)
        end_time = time.time()
        logging.info("renew dictionary with unseen news tokens, and serialized in path -> {}, "
                     "which took {} mins ... ".format(ori_dict_path, (end_time-start_time)/60))

        unseen_bow_vector = [updated_dictionary_with_old_and_unseen_news.doc2bow(doc_token) for doc_token in
                             unssen_documents_token_list]
        updated_bow_vector_with_old_and_unseen_news = []
        updated_bow_vector_with_old_and_unseen_news.extend(historical_bow_vec)
        updated_bow_vector_with_old_and_unseen_news.extend(unseen_bow_vector)
        # 原先updated_bow_vector_with_old_and_unseen_news是list类型，
        # 但是经过下面序列化后重新加载进来的类型是gensim.corpora.mmcorpus.MmCorpus
        if is_saved_bow_vector and bowvec_save_path:
            corpora.MmCorpus.serialize(bowvec_save_path,
                                       updated_bow_vector_with_old_and_unseen_news)  # 保存更新后的bow向量，即包括新旧新闻的bow向量集
        logging.info("combined bow vector(type -> 'list') generated by historical news with unseen bow "
                     "vector to create a new one ... ")

        if topic_model_type == "lsi":
            start_time = time.time()
            updated_tfidf_model_vector = self.transform_vectorized_corpus(updated_dictionary_with_old_and_unseen_news,
                                                                          updated_bow_vector_with_old_and_unseen_news,
                                                                          model_type="tfidf")  # type -> <gensim.interfaces.TransformedCorpus object>
            end_time = time.time()
            logging.info("regenerated TF-IDF model vector by updated dictionary and updated bow-vector, "
                         "which took {} mins ... ".format((end_time-start_time)/60))

            start_time = time.time()
            model = models.LsiModel(updated_tfidf_model_vector,
                                    id2word=updated_dictionary_with_old_and_unseen_news,
                                    num_topics=config.TOPIC_NUMBER)  # 初始化模型
            model_vector = model[updated_tfidf_model_vector]  # type -> <gensim.interfaces.TransformedCorpus object>
            end_time = time.time()
            logging.info("regenerated LSI model vector space by updated TF-IDF model vector space, "
                         "which took {} mins ... ".format((end_time-start_time)/60))
        elif topic_model_type == "lda":
            start_time = time.time()
            model_vector = self.transform_vectorized_corpus(updated_dictionary_with_old_and_unseen_news,
                                                            updated_bow_vector_with_old_and_unseen_news,
                                                            model_type="lda")
            end_time = time.time()
            logging.info("regenerated LDA model vector space by updated dictionary and bow-vector, "
                         "which took {} mins ... ".format((end_time-start_time)/60))

        # 将gensim.interfaces.TransformedCorpus类型的lsi模型向量转为numpy矩阵
        start_time = time.time()
        latest_matrix = corpus2dense(model_vector,
                                     num_terms=model_vector.obj.num_terms).T
        end_time = time.time()
        logging.info("transform {} model vector space to numpy.adarray, "
                     "which took {} mins ... ".format(topic_model_type.upper(), (end_time-start_time)/60))

        # 利用历史数据的话题模型向量(或特征)，进一步训练新闻分类器
        start_time = time.time()
        train_x, train_y, test_x, test_y = utils.generate_training_set(latest_matrix[:-1, :], Y)
        clf = self.classifier.train(train_x, train_y, test_x, test_y, model_type=classifier_model)
        end_time = time.time()
        logging.info("finished training by sklearn {} using latest {} model vector space, which took {} mins ... "
                     .format(classifier_model.upper(), topic_model_type.upper(), (end_time-start_time)/60))

        label_id = clf.predict(latest_matrix[-1, :].reshape(1, -1))[0]

        return label_name_list[label_id]


if __name__ == "__main__":
    label_name = "3DaysLabel"
    database_name = "stocknews"
    # sh600004的数据量比较少，可作为跑通代码流程的参数；sz000001的数据量比较大，处理起来也较慢，可以作为后续案例测试
    collection_name = "sz000001"
    classifier_save_path = "{}_classifier.pkl".format(collection_name)
    ori_dict_path = "{}_docs_dict.dict".format(collection_name)
    bowvec_save_path = "{}_bowvec.mm".format(collection_name)

    # 对(未见过的)新闻进行分类
    # unseen_raw_documents_list = ["智通财经APP讯，白云机场(600004.SH)发布公告，公司2020年11月起降40278架次，\
    #                               同比下降2.47%;旅客吞吐量约501.4万人次，同比下降19.31%;货邮吞吐量约17.32万\
    #                               吨，同比下降1.27%。此外，公司2020年累计起降约33.2万架次，同比下降26.07%;旅\
    #                               客吞吐量约3890.14万人次，同比下降42.00%;货邮吞吐量约158.12万吨，同比下降9.14%。",
    #                              "格隆汇 9 月 1日丨白云机场(600004.SH)公布，公司收到中国证券监督管理委员会于2020\
    #                               年8月20日出具的《中国证监会行政许可项目审查一次反馈意见通知书》(202137号)。根据\
    #                               《反馈意见》的相关要求，白云机场控股股东广东省机场管理集团有限公司(“机场集团”)\
    #                               于2020年8月31日出具了《广东省机场管理集团有限公司关于不存在减持广州白云国际机场股\
    #                               份有限公司股票行为或减持计划的承诺函》，具体内容如下：鉴于机场集团拟以现金的方式参\
    #                               与认购本次白云机场非公开发行的A股股票。机场集团现作出如下承诺：1、自白云机场本次发\
    #                               行定价基准日(即2020年4月28日)前六个月至本承诺函出具之日，机场集团及机场集团控制的关\
    #                               联方未出售或以任何方式减持白云机场的任何股票。2、自本承诺函出具之日起至白云机场本次发\
    #                               行完成后六个月期间内，机场集团及机场集团控制的关联方将不会出售或以任何方式减持所持有的\
    #                               白云机场的任何股票，也不存在减持白云机场股票的计划。3、机场集团及机场集团控制的关联方\
    #                               不存在违反《中华人民共和国证券法》第四十四条的情形。如有违反，机场集团因减持股票所得收\
    #                               益将归白云机场所有。4、本承诺函自签署之日起对机场集团具有约束力，若机场集团或机场集团\
    #                               控制的关联方违反上述承诺发生减持情况，则减持所得全部收益归白云机场所有，机场集团依法\
    #                               承担由此产生的法律责任。",
    #                              "格隆汇11月27日丨白云机场(600004.SH)公布，为增强上市公司经营独立性、业务及资产完整性，\
    #                              提升公司盈利能力与运行保障能力，扩展白云机场物流业务发展空间，同时减少关联交易，确保上\
    #                              市公司利益最大化，公司拟实施如下交易：机场集团以所持有的航合公司100%的股权以及铂尔曼酒\
    #                              店、澳斯特酒店相应的经营性资产及负债与上市公司所持有的物流公司51%的股权进行资产置换，差\
    #                              额部分以现金补足。其中航合公司100%股权作价7.54亿元，铂尔曼酒店经营性资产及负债作价2.28\
    #                              亿元，澳斯特酒店经营性资产及负债作价3950.01万元，物流公司51%股权作价8.57亿元，上市公司\
    #                              需向机场集团以现金方式支付差额1.64亿元。本次交易完成后，公司将持有航合公司100%股权、铂\
    #                              尔曼酒店和澳斯特酒店经营性资产及负债、物流公司49%股权；机场集团将持有物流公司51%股权。\
    #                              本次交易除上述资产置换外，还包括：(1)上市公司与机场集团重新划分国内航空主业收入中旅客服\
    #                              务费(以下简称“旅客服务费”)的分成比例，由上市公司占85%、机场集团占15%，变更为上市公司\
    #                              占100%，机场集团不再享有旅客服务费分成，2018年15%旅客服务费对应金额为1.19亿元；及(2)上\
    #                              市公司将按物流公司年营业收入的4%向物流公司收取经营权使用费。2018年，模拟计算物流公司营\
    #                              业收入4%对应的经营权使用费为2536.07万元。本次资产置换交易完成后，上市公司2018年备考口径\
    #                              净利润、归母净利润、净资产、归母净资产和每股收益都将增厚约5%，2018年备考每股收益将从\
    #                              0.5457元每股增厚至0.5717元每股。为充分保障上市公司及中小股东利益，机场集团同意，自本次\
    #                              资产置换交割之日起五年内，上市公司享有一次回购物流公司股权的权利，即上市公司有权要求机\
    #                              场集团将本次交易取得的全部物流公司股权(对应同等金额的注册资本金额，包括在此基础上进行\
    #                              配股、转增、折股等所取得的股权)按届时评估值转让给上市公司。因此，上市公司在本次资产置\
    #                              换中拥有充分的主动权，可以选择重新取得物流公司的控制权。据悉，旅客服务费是公司主营航空\
    #                              性业务收入的重要组成部分，对业务完整性具有重要意义。旅客服务费全部由上市公司享有后，将\
    #                              较大幅度增加上市公司的收入、利润和现金流水平。受益于粤港澳大湾区规划及白云机场T2航站楼\
    #                              启用，旅客吞吐量逐年提升。未来随着白云机场的T3航站楼及新跑道的建设推进，旅客吞吐量还将\
    #                              进一步提升，15%旅客服务费对应收入将随之提升，并为公司贡献更多业绩增长空间。"]

    unseen_raw_documents_list = ["格隆汇6月23日丨平安银行(000001.SZ)公布，近日收到《中国银保监会关于平安银行变更注册资本\
                                 的批复》(银保监复〔2020〕342号)，中国银行保险监督管理委员会同意本行将注册资本由人民币\
                                 17, 170, 411, 366元增加至19, 405, 918, 198元，并修改本行章程相应条款。",
                                 "平安银行(000001,股吧)(000001.SZ)公布，公司于2020年8月19日收到《中国银保监会关于平安理\
                                 财有限责任公司开业的批复》(银保监复〔2020〕513号)，中国银行保险监督管理委员会(简称“中\
                                 国银保监会”)已批准公司全资子公司平安理财有限责任公司(简称“平安理财”)开业。根据中国银\
                                 保监会批复，平安理财注册资本为50亿元人民币，注册地为深圳市，主要从事发行公募理财产品、\
                                 发行私募理财产品、理财顾问和咨询等资产管理相关业务。　　近年来，公司以打造“中国最卓越\
                                 、全球领先的智能化零售银行”为战略目标，坚持“科技引领、零售突破、对公做精”十二字策略\
                                 方针，强化“综合金融”、“科技赋能”两大核心优势，打造数字化银行、生态银行、平台银行三\
                                 张名片，推动发展迈向新台阶。在此基础上，稳步推进资产管理和理财业务转型，综合服务能力不\
                                 断提升，规模、质量、效益实现协调发展。设立平安理财是本行严格落实监管要求、促进理财业务\
                                 健康发展、推动理财业务回归本源的重要举措。平安理财将秉持“受人之托，代客理财”的服务宗\
                                 旨，深耕理财市场，为客户提供更优质的资管产品和财富管理服务，助力实体经济高质量发展。下\
                                 一步，公司将按照法律法规相关要求严格履行有关程序，推动平安理财尽快开业运营。",
                                 "格隆汇5月26日丨平安银行(000001.SZ)公布，经中国银行保险监督管理委员会和中国人民银行批准\
                                 ，公司于近日在全国银行间债券市场成功发行了总额为300亿元人民币的小型微型企业贷款专项金融\
                                 债券。该期债券发行总规模为人民币300亿元，为3年期固定利率债券，票面利率为2.30%，募集资金\
                                 将依据适用法律和监管部门的批准，专项用于发放小型微型企业贷款，其中部分将用于发放与新冠\
                                 肺炎疫情防控相关的小微企业贷款，加大对小型微型企业信贷支持力度，推动小型微型企业业务稳\
                                 健、健康发展。"]

    topicmodelling = TopicModelling()
    for unseen_doc in unseen_raw_documents_list:
        chn_label = topicmodelling.classify_stock_news(unseen_doc,
                                                       database_name,
                                                       collection_name,
                                                       label_name=label_name,
                                                       topic_model_type="lsi",
                                                       classifier_model="rdforest",  # rdforest / svm
                                                       ori_dict_path=ori_dict_path,
                                                       bowvec_save_path=bowvec_save_path)
        logging.info("document '{}...' was classified with label '{}' for symbol {} ... ".format(unseen_doc[:20], chn_label, collection_name))

    # lsi Tue, 15 Dec 2020 14:54:08 classifier.py[line:54] INFO train_pred: 0.9829  test_pred: 0.703 (只是去掉停用词、tab符以及空格符) 30DaysLabel
    # lsi Tue, 15 Dec 2020 17:00:58 classifier.py[line:54] INFO train_pred: 0.9852  test_pred: 0.7492(去掉不含中文的词以及只有一个字符的词) 30DaysLabel
    # lda Tue, 15 Dec 2020 17:29:56 classifier.py[line:54] INFO train_pred: 0.9498  test_pred: 0.7426(去掉不含中文的词以及只有一个字符的词) 30DaysLabel
    # lsi Wed, 16 Dec 2020 15:57:28 classifier.py[line:54] INFO train_pred: 0.9872  test_pred: 0.7478(修改create_dictionary后) 30DaysLabel
    # lsi Wed, 16 Dec 2020 17:14:57 classifier.py[line:54] INFO train_pred: 0.9777  test_pred: 0.7247(修改create_dictionary后) 3DaysLabel
    # lsi Wed, 16 Dec 2020 17:30:15 classifier.py[line:54] INFO train_pred: 0.9883  test_pred: 0.7123(修改create_dictionary后) 60DaysLabel
