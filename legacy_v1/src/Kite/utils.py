import re
import datetime
import requests
import numpy as np
from bs4 import BeautifulSoup
from scipy.sparse import csr_matrix


def generate_pages_list(total_pages, range, init_page_id):
    page_list = list()
    k = init_page_id

    while k + range - 1 <= total_pages:
        page_list.append((k, k + range -1))
        k += range

    if k + range - 1 < total_pages:
        page_list.append((k, total_pages))

    return page_list


def count_chn(string):
    '''Count Chinese numbers and calculate the frequency of Chinese occurrence.

    # Arguments:
        string: Each part of crawled website analyzed by BeautifulSoup.
    '''
    pattern = re.compile(u'[\u1100-\uFFFDh]+?')
    result = pattern.findall(string)
    chn_num = len(result)
    possible = chn_num / len(str(string))

    return chn_num, possible


def get_date_list_from_range(begin_date, end_date):
    '''Get date list from 'begin_date' to 'end_date' on the calendar.
    '''
    date_list = list()
    begin_date = datetime.datetime.strptime(begin_date, "%Y-%m-%d")
    end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d")
    while begin_date <= end_date:
        date_str = begin_date.strftime("%Y-%m-%d")
        date_list.append(date_str)
        begin_date += datetime.timedelta(days=1)

    return date_list


def gen_dates_list(date_list, date_range):
    date_list_latest = list()
    k = 0
    while k < len(date_list):
        if k + date_range >= len(date_list):
            break
        else:
            date_list_latest.append(date_list[k: k + date_range])
            k += date_range
    date_list_latest.append(date_list[k:])

    return date_list_latest


def get_date_before(n_days):
    """
    获取前n_days天的日期，如今天是2020-12-25，当n_days=1，返回"2020-12-24"
    :param n_days: 前n_days天数，如n_days=1，即前1天
    """
    today = datetime.datetime.now()
    # 计算偏移量
    offset = datetime.timedelta(days=-n_days)
    # 获取想要的日期的时间
    re_date = (today + offset).strftime('%Y-%m-%d')
    return re_date


def search_max_pages_num(first_url, date):
    """
    主要针对金融界网站
    通过日期搜索新闻，比如2020年1月1日的新闻，下面链接
    http://stock.jrj.com.cn/xwk/202001/20200101_1.shtml
    为搜索返回的第一个网页，通过这个网页可以发现，数据库
    返回的最大页数是4，即2020年1月1日共有4页的新闻列表
    :param first_url: 搜索该日期返回的第一个网址，如'http://stock.jrj.com.cn/xwk/202001/20200101_1.shtml'
    :param date: 日期，如'2020-01-01'
    """
    respond = requests.get(first_url)
    respond.encoding = BeautifulSoup(respond.content, "lxml").original_encoding
    bs = BeautifulSoup(respond.text, "lxml")
    a_list = bs.find_all("a")
    max_pages_num = 1
    for a in a_list:
        if "href" in a.attrs and "target" in a.attrs:
            if a["href"].find(date.replace("-", "") + "_") != -1 \
                    and a.text.isdigit():
                max_pages_num += 1

    return max_pages_num


def html_parser(url):
    resp = requests.get(url)
    resp.encoding = BeautifulSoup(resp.content, "lxml").original_encoding
    bs = BeautifulSoup(resp.text, "lxml")

    return bs


def get_chn_stop_words(path):
    '''Load the stop words txt file.
    '''
    stopwords = [line.strip() for line in open(path, 'r').readlines()]

    return stopwords


def convert_to_csr_matrix(model_vector):
    """
    Convert LDA(LSI) model vector to CSR sparse matrix, that could be accepted by Scipy and Numpy.

    # Arguments:
        modelVec: Transformation model vector, such as LDA model vector, tfidf model vector or lsi model vector.
    """
    data = []
    rows = []
    cols = []
    _line_count = 0
    for line in model_vector:  # line=[(int, float), (int, float), ...]
        for elem in line:  # elem=(int, float)
            rows.append(_line_count)
            cols.append(elem[0])
            data.append(elem[1])
        _line_count += 1
    sparse_matrix = csr_matrix((data, (rows, cols)))
    matrix = sparse_matrix.toarray()  # <class 'numpy.ndarray'>

    return matrix


def generate_training_set(x, y, split=0.8):
    rand = np.random.random(size=x.shape[0])
    train_x = []
    train_y = []
    test_x = []
    test_y = []
    for i in range(x.shape[0]):
        if rand[i] < split:
            train_x.append(x[i, :])
            train_y.append(y[i])
        else:
            test_x.append(x[i, :])
            test_y.append(y[i])
    return train_x, train_y, test_x, test_y


def is_contain_chn(word):
    """
    判断传入字符串是否包含中文
    :param word: 待判断字符串
    :return: True:包含中文  False:不包含中文
    """
    zh_pattern = re.compile(u'[\u4e00-\u9fa5]+')
    if zh_pattern.search(word):
        return True
    else:
        return False


def batch_lpop(client, key, n):
    p = client.pipeline()
    p.lrange(key, 0, n-1)
    p.ltrim(key, n, -1)
    p.execute()
