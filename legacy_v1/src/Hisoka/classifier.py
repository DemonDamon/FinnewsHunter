import __init__
import logging
import warnings

from Kite import config

import joblib
from sklearn import svm
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GridSearchCV
from sklearn.metrics import classification_report
import sklearn.exceptions

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s",
                    datefmt="%a, %d %b %Y %H:%M:%S")

warnings.filterwarnings("ignore", category=sklearn.exceptions.UndefinedMetricWarning)
warnings.filterwarnings("ignore", category=Warning, module='sklearn')
warnings.filterwarnings("ignore", category=UserWarning, module='gensim')
warnings.filterwarnings("ignore", category=RuntimeWarning, module='gensim')


class Classifier(object):

    def __init__(self):
        self.scores = config.CLASSIFIER_SCORE_LIST

    def train(self, train_x, train_y, test_x, test_y, model_type="svm", model_save_path=None):
        assert len(self.scores) != 0
        clf = None
        for score in self.scores:
            # 'cv': 构造这个GridSearch的分类器,5-fold
            # 'refit': 默认为True,程序将会以交叉验证训练集得到的最佳参数，重新对所有可用的训练，
            #          作为最终用于性能评估的最佳模型参数。即在搜索参数结束后，用最佳参数结果再
            #          次fit一遍全部数据集
            if model_type == "svm":
                tuned_parameters = config.SMV_TUNED_PARAMTERS
                clf = GridSearchCV(svm.SVC(),
                                   tuned_parameters,
                                   cv=5,
                                   scoring=score,
                                   refit="AUC")
            elif model_type == "rdforest":
                tuned_parameters = config.RDFOREST_TUNED_PARAMTERS
                clf = GridSearchCV(RandomForestClassifier(random_state=10),
                                   tuned_parameters,
                                   cv=5,
                                   scoring=score,
                                   refit="AUC")
            # 只在训练集上面做k-fold,然后返回最优的模型参数
            clf.fit(train_x, train_y)
            if model_save_path is not None:
                joblib.dump(clf, model_save_path)
            # 输出最优的模型参数
            logging.info("the best params: {}".format(clf.best_params_))
            train_pred = clf.predict(train_x)
            test_pred = clf.predict(test_x)  # 在测试集上测试最优的模型的泛化能力
            logging.info("\n{}".format(classification_report(test_y, test_pred)))
            precise_train = 0
            for k in range(len(train_pred)):
                if train_pred[k] == train_y[k]:
                    precise_train += 1
            precise_test = 0
            for k in range(len(test_pred)):
                if test_pred[k] == test_y[k]:
                    precise_test += 1
            logging.info('train_accuracy: {}  test_accuracy: {}'
                         .format(str(round(precise_train / len(train_y), 4)),
                                 str(round(precise_test / len(test_pred), 4))))
            self._precise = precise_test / len(test_pred)
        assert clf is not None
        return clf

    @staticmethod
    def model_load(classifier_save_path):
        return joblib.load(classifier_save_path)