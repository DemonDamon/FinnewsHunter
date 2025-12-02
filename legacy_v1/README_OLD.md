# 上市公司新闻文本分析与分类预测

 ![image](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/assets/images/FINNEWS-HUNTER.jpg)

[![Star History Chart](https://api.star-history.com/svg?repos=DemonDamon/Listed-company-news-crawl-and-text-analysis&type=Date)]([https://star-history.com/#linhandev/dataset&Date](https://star-history.com/#DemonDamon/Listed-company-news-crawl-and-text-analysis&Date))

-------------------------------

## 简介

上市公司新闻文本分析与分类预测的基本步骤如下：

 - 从新浪财经、每经网、金融界、中国证券网、证券时报网上，爬取上市公司（个股）的历史新闻文本数据（包括时间、网址、标题、正文）
 - 从Tushare上获取沪深股票日线数据（开、高、低、收、成交量和持仓量）和基本信息（包括股票代码、股票名称、所属行业、所属地区、PE值、总资产、流动资产、固定资产、留存资产等）
 - 对抓取的新闻文本按照，去停用词、加载新词、分词的顺序进行处理
 - 利用前两步中所获取的股票名称和分词后的结果，抽取出每条新闻里所包含的（0支、1支或多支）股票名称，并将所对应的所有股票代码，组合成与该条新闻相关的股票代码列表，并在历史数据表中增加一列相关股票代码数据
 - 从历史新闻数据库中抽取与某支股票相关的所有新闻文本，利用该支股票的日线数据（比如某一天发布的消息，在设定N天后如果价格上涨则认为是利好消息，反之则是利空消息）给每条新闻贴上“利好”和“利空”的标签，并存储到新的数据库中（或导出到CSV文件）
 - 实时抓取新闻数据，判断与该新闻相关的股票有哪些，利用上一步的结果，对与某支股票相关的所有历史新闻文本（已贴标签）进行文本分析（构建新的特征集），然后利用SVM（或随机森林）分类器对文本分析结果进行训练（如果已保存训练模型，可选择重新训练或直接加载模型），最后利用训练模型对实时抓取的新闻数据进行分类预测

开发环境`Python-v3(3.6)`：

 - gensim==3.2.0
 - jieba==0.39
 - scikit-learn==0.19.1
 - pandas==0.20.0
 - numpy==1.13.3+mkl
 - scipy==0.19.0
 - pymongo==3.6.0
 - beautifulsoup4==4.6.0
 - tushare==1.1.1
 - requests==2.18.4
 - gevent==1.2.1

## 文本处理 -> [text_processing.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/Text_Analysis/text_processing.py)

 - 文本处理包括去停用词处理、加载新词、中文分词、去掉出现次数少的分词
 - 生成字典和Bow向量，并基于Gensim转化模型（LSI、LDA、TF-IDF）转化Bow向量
 - 计算文本相似度
 - 打印词云

## 文本挖掘 -> [text_mining.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/Text_Analysis/text_mining.py)

 - 从新闻文本中抽取特定信息，并贴上新的文本标签方便往后训练模型
 - 从数据库中抽取与某支股票相关的所有新闻文本
 - 将贴好标签的历史新闻进行分类训练，利用训练好的模型对实时抓取的新闻文本进行分类预测

## 新闻爬取 -> [crawler_cnstock.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/Crawler/crawler_cnstock.py), [crawler_jrj.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/Crawler/crawler_jrj.py), [crawler_nbd.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/Crawler/crawler_nbd.py), [crawler_sina.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/Crawler/crawler_sina.py), [crawler_stcn.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/Crawler/crawler_stcn.py)

 - 分析网站结构，多线程（或协程）爬取上市公司历史新闻数据

## Tushare数据提取 -> [crawler_tushare.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/run_crawler_tushare.py)

 - 获取沪深所有股票的基本信息，包括股票代码、股票名称、所属行业、所属地区等

## 用法

 - 配好运行环境以及安装MongoDB，最好再安装一个MongoDB的可视化管理工具Studio 3T
 - 先运行[crawler_cnstock.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/Crawler/crawler_cnstock.py), [crawler_jrj.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/Crawler/crawler_jrj.py), [crawler_nbd.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/Crawler/crawler_nbd.py), [crawler_sina.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/Crawler/crawler_sina.py), [crawler_stcn.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/Crawler/crawler_stcn.py)这5个py文件，而且可能因为对方服务器没有响应而重复多次运行这几个文件才能抓取大量的历史数据
 - 接着运行[crawler_tushare.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/run_crawler_tushare.py)从Tushare获取基本信息和股票价格
 - 最后运行[run_main.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/run_main.py)文件，其中有4个步骤，除了第1步初始化外，其他几步最好单独运行
 - 注意：所有程序都必须在文件所在目录下运行

## 更新目标

 由于之前的项目代码是在初学Python的时候写的，很多写法都是入门级别，因此为了提高整体项目的质量，除了优化代码细节和已有的功能模块之外，还加入了多个功能模块，来支撑未来更加智能化和个性化的金融分析与交易。
 - 完成初步构想，重构该项目，将项目分成8大模块，分别是`数据获取模块`，`数据清洗与预处理模块`，`大数据可视化模块`，`基于机器学习的文本挖掘模块`，`金融知识图谱构建模块`，`任务导向多轮对话模块`，`金融交易模块`，`通用服务模块`
 (备注：项目在完善之后会重新更名为`Finnews Hunter`，命名的来源是出于对`《全职猎人》`的喜爱，与项目本质的结合，其中`Finnews`是`Financial News`的简写。上面提到的8个模块，分别由`《全职猎人》`中的本人最喜爱的8位角色命名，分别是
 - `数据获取模块`               -> [Gon](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/tree/main/src/Gon) -> `网页爬虫、各种数据源API调用等`
 - `数据清洗与预处理模块`       -> [Killua](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/tree/main/src/Killua) -> `数据清洗、数据转换(数据采样、类型转换、归一化等)、数据描述(数据可视化)、特征选择与组合(熵增益和分支定界等)、特征抽取(主成分分析、线性判别分析等)`
 - `大数据可视化模块`           -> [Kurapika](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/tree/main/src/Kurapika) -> `基于多个可视化模块进行封装，包括提供Web可视化界面`
 - `自然语言处理模块`           -> [Leorio](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/tree/main/src/Leorio) -> `中文分词、词性标注、实体识别`
 - `基于机器学习的文本挖掘模块` -> [Hisoka](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/tree/main/src/Hisoka)  -> ``
 - `金融知识图谱构建模块`       -> [Chrollo](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/tree/main/src/Chrollo) -> ``
 - `任务导向多轮对话模块`       -> [Illumi](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/tree/main/src/Illumi) -> ``
 - `金融交易模块`               -> [Feitan](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/tree/main/src/Feitan) -> ``
 - `基础与Web服务模块`          -> [Kite](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/tree/main/src/Kite) -> `基础服务集，包括基本参数配置文件(.py)、数据库的构建与连接、日志打印与收集、多线程服务、Web服务框架搭建以及其他函数`)
 
 ## 更新日志
 - 注意：  
   - 以下例子均需在代码根目录[src](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/tree/main/src)下执行  
   - 先安装好MongoDB用作存储数据库，以及Redis用做简单的消息队列
   - 运行下面demo时，先要设置[config.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/src/Kite/config.py)里面的参数
   
 - 更新[crawler_tushare.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/Crawler/crawler_tushare.py)代码为[stockinfospyder.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/src/Gon/stockinfospyder.py)，直接运行即可获取股票历史价格数据，并在每天15:30分后更新数据(目前只采集天数据)
    - example-1 调用[AkShare](https://www.akshare.xyz/zh_CN/latest/)接口获取股票历史价格数据，并开启实时更新
    ```
    from Kite import config
    from Gon.stockinfospyder import StockInfoSpyder

    stock_info_spyder = StockInfoSpyder(config.STOCK_DATABASE_NAME, config.COLLECTION_NAME_STOCK_BASIC_INFO)
    # 指定时间段，获取历史数据，如：stock_info_spyder.get_historical_news(start_date="20150101", end_date="20201204")
    # 如果没有指定时间段，且数据库已存在部分数据，则从最新的数据时间开始获取直到现在，比如数据库里已有sh600000价格数据到
    # 2020-12-03号，如不设定具体时间，则从自动获取sh600000自2020-12-04至当前的价格数据
    stock_info_spyder.get_historical_news()
    ```
    - example-2 开启自动化更新所有股票价格数据(目前只支持在15:30分后更新日数据)
    ```
    from Kite import config
    from Gon.stockinfospyder import StockInfoSpyder

    stock_info_spyder = StockInfoSpyder(config.STOCK_DATABASE_NAME, config.COLLECTION_NAME_STOCK_BASIC_INFO)
    stock_info_spyder.get_realtime_news()
    ```
 - 更新[crawler_cnstock.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/Crawler/crawler_cnstock.py)代码为[cnstockspyder.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/src/Gon/cnstockspyder.py)，直接运行即可获取中国证券网历史新闻数据，并可以实时更新采集
    - example-1 爬取历史新闻数据，然后去重以及去NULL
    ```
    import time
    import logging
    from Kite import config
    from Killua.denull import DeNull
    from Killua.deduplication import Deduplication 
    from Gon.cnstockspyder import CnStockSpyder

    cnstock_spyder = CnStockSpyder(config.DATABASE_NAME, config.COLLECTION_NAME_CNSTOCK)
    for url_to_be_crawled, type_chn in config.WEBSITES_LIST_TO_BE_CRAWLED_CNSTOCK.items():
        logging.info("start crawling {} ...".format(url_to_be_crawled))
        cnstock_spyder.get_historical_news(url_to_be_crawled, category_chn=type_chn)
        logging.info("finished ...")
        time.sleep(30)

    Deduplication(config.DATABASE_NAME, config.COLLECTION_NAME_CNSTOCK).run()
    DeNull(config.DATABASE_NAME, config.COLLECTION_NAME_CNSTOCK).run()
    ```
    - example-2 实时更新新闻数据库，并且将新数据推进redis消息队列等待处理
    ```
    import time, logging, threading
    from Kite import config
    from Kite.database import Database
    from Killua.denull import DeNull
    from Killua.deduplication import Deduplication 
    from Gon.cnstockspyder import CnStockSpyder

    obj = Database()
    df = obj.get_data(config.DATABASE_NAME, config.COLLECTION_NAME_CNSTOCK, keys=["Date", "Category"])

    cnstock_spyder = CnStockSpyder(config.DATABASE_NAME, config.COLLECTION_NAME_CNSTOCK)
    # 先补充历史数据，比如已爬取数据到2020-12-01，但是启动实时爬取程序在2020-12-23，则先
    # 自动补充爬取2020-12-02至2020-12-23的新闻数据
    for url_to_be_crawled, type_chn in config.WEBSITES_LIST_TO_BE_CRAWLED_CNSTOCK.items():
        # 查询type_chn的最近一条数据的时间
        latets_date_in_db = max(df[df.Category == type_chn]["Date"].to_list())
        cnstock_spyder.get_historical_news(url_to_be_crawled, category_chn=type_chn, start_date=latets_date_in_db)

    Deduplication(config.DATABASE_NAME, config.COLLECTION_NAME_CNSTOCK).run()
    DeNull(config.DATABASE_NAME, config.COLLECTION_NAME_CNSTOCK).run()

    # 开启多线程并行实时爬取
    thread_list = []
    for url, type_chn in config.WEBSITES_LIST_TO_BE_CRAWLED_CNSTOCK.items():
        thread = threading.Thread(target=cnstock_spyder.get_realtime_news, args=(url, type_chn, 60))
        thread_list.append(thread)
    for thread in thread_list:
        thread.start()
    for thread in thread_list:
        thread.join()
    ```
 - 更新[crawler_jrj.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/Crawler/crawler_jrj.py)代码为[jrjspyder.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/src/Gon/jrjspyder.py)，直接运行即可获取金融界历史新闻数据，并可以实时更新采集
    - example-1 爬取历史新闻数据，然后去重以及去NULL
    ```
    from Kite import config
    from Killua.denull import DeNull
    from Killua.deduplication import Deduplication 
    from Gon.jrjspyder import JrjSpyder

    jrj_spyder = JrjSpyder(config.DATABASE_NAME, config.COLLECTION_NAME_JRJ)
    jrj_spyder.get_historical_news(config.WEBSITES_LIST_TO_BE_CRAWLED_JRJ, start_date="2015-01-01")

    Deduplication(config.DATABASE_NAME, config.COLLECTION_NAME_JRJ).run()
    DeNull(config.DATABASE_NAME, config.COLLECTION_NAME_JRJ).run()
    ```
    - example-2 已爬取一定量的历史数据下，开启实时更新新闻数据库，并且将新数据推进redis消息队列等待处理
    ```
    from Kite import config
    from Gon.jrjspyder import JrjSpyder

    jrj_spyder = JrjSpyder(config.DATABASE_NAME, config.COLLECTION_NAME_JRJ)
    jrj_spyder.get_historical_news(config.WEBSITES_LIST_TO_BE_CRAWLED_JRJ)  # 补充爬虫数据到最新日期
    jrj_spyder.get_realtime_news()
    ```
 - 更新[crawler_nbd.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/Crawler/crawler_nbd.py)代码为[nbdspyder.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/src/Gon/nbdspyder.py)，直接运行即可获取每经网历史新闻数据，并可以实时更新采集
    - example-1 爬取历史新闻数据，然后去重以及去NULL
    ```
    from Kite import config
    from Killua.denull import DeNull
    from Killua.deduplication import Deduplication 
    from Gon.nbdspyder import NbdSpyder

    nbd_spyder = NbdSpyder(config.DATABASE_NAME, config.COLLECTION_NAME_NBD)
    nbd_spyder.get_historical_news(start_page=684)

    Deduplication(config.DATABASE_NAME, config.COLLECTION_NAME_NBD).run()
    DeNull(config.DATABASE_NAME, config.COLLECTION_NAME_NBD).run()
    ```
    - example-2 已爬取一定量的历史数据下，开启实时更新新闻数据库，并且将新数据推进redis消息队列等待处理
    ```
    from Kite import config
    from Killua.denull import DeNull
    from Killua.deduplication import Deduplication 
    from Gon.nbdspyder import NbdSpyder

    # 如果没有历史数据从头爬取，如果已爬取历史数据，则从最新的时间开始爬取
    # 如历史数据中最近的新闻时间是"2020-12-09 20:37:10"，则从该时间开始爬取
    nbd_spyder = NbdSpyder(config.DATABASE_NAME, config.COLLECTION_NAME_NBD)
    nbd_spyder.get_historical_news()

    Deduplication(config.DATABASE_NAME, config.COLLECTION_NAME_NBD).run()
    DeNull(config.DATABASE_NAME, config.COLLECTION_NAME_NBD).run()

    nbd_spyder.get_realtime_news()
    ```
 - 更新[crawler_sina.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/Crawler/crawler_sina.py)代码为[sinaspyder.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/src/Gon/sinaspyder.py)，直接运行即可获取新浪财经历史新闻数据(未更新)
 - 停止`证券时报网`爬虫代码的更新(旧代码已不可用)，新增`网易财经`和`凤凰财经`的爬虫代码(未更新)
 - 新增[buildstocknewsdb.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/src/Killua/buildstocknewsdb.py)如果已经在每经网、中国证券网和金融界爬取了一定量新闻文本，接下来就是针对每支股票构建对应的新闻数据库，并根据股价贴上3/5/10/15/30/60天标签，具体判断条件查看[buildstocknewsdb.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/src/Killua/buildstocknewsdb.py)第111-116行注释
    - example-1 从历史新闻数据库中抽取、构建每支股票的新闻数据库，并贴上标签
    ```
    from Kite import config
    from Killua.buildstocknewsdb import GenStockNewsDB

    gen_stock_news_db = GenStockNewsDB()
    gen_stock_news_db.get_all_news_about_specific_stock(config.DATABASE_NAME, config.COLLECTION_NAME_CNSTOCK)
    gen_stock_news_db.get_all_news_about_specific_stock(config.DATABASE_NAME, config.COLLECTION_NAME_NBD)
    gen_stock_news_db.get_all_news_about_specific_stock(config.DATABASE_NAME, config.COLLECTION_NAME_JRJ)
    ```
    - example-2 监听redis消息队列，将新的数据分别存入与该新闻相关的所有股票新闻数据库中
    ```
    from Kite import config
    from Killua.buildstocknewsdb import GenStockNewsDB

    gen_stock_news_db = GenStockNewsDB()
    gen_stock_news_db.listen_redis_queue()
    ```
 - 新增[realtime_spyder_startup.bat](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/src/realtime_spyder_startup.bat)同时以下程序
    - 开启多个爬虫实例，包括[realtime_starter_cnstock.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/src/Gon/realtime_starter_cnstock.py)、[realtime_starter_jrj.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/src/Gon/realtime_starter_jrj.py)、[realtime_starter_nbd.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/src/Gon/realtime_starter_nbd.py)等
    - 全股票数据更新代码[realtime_starter_stock_price.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/src/Gon/realtime_starter_stock_price.py)
    - 监听redis消息队列[realtime_starter_redis_queue.py](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/src/Gon/realtime_starter_redis_queue.py)
  - 新增[realtime_spyder_stopall.bat](https://github.com/DemonDamon/Listed-company-news-crawl-and-text-analysis/blob/main/src/realtime_spyder_stopall.bat)批量终止爬虫程序
 - 更新前使用jieba分词系统，在实体识别上需要不断维护新词表来提高识别精度；更新后，使用基于BERT预训练的FinBERT对金融领域实体进行识别

# FinnewsHunter (Reborn)

基于 AgenticX 框架构建的企业级多智能体金融决策平台。

## 项目状态

🚧 **重构进行中** 🚧

本项目正在经历重大重构，从单一脚本集合升级为现代化的微服务架构。

- **旧版代码**：已归档至 `legacy_v1/` 目录。
- **重构规划**：详见 [planning.md](../../planning.md)。

## 技术架构

- **后端**: Python, FastAPI, AgenticX (Orchestrator, Debate, Tools)
- **前端**: TypeScript, React
- **算法**: sklearn, PyTorch, vllm

## 快速开始

### 后端开发

1. 进入后端目录：
   ```bash
   cd backend
   ```
2. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
3. 启动服务：
   ```bash
   uvicorn app.main:app --reload
   ```

## 目录结构

```
FinnewsHunter/
├── backend/            # FastAPI 后端服务
│   ├── app/            # 应用代码
│   └── tests/          # 测试用例
├── frontend/           # React 前端应用 (待初始化)
├── legacy_v1/          # 旧版代码归档
├── docs/               # 项目文档
└── README.md           # 项目说明
```

### 快速开始

1. 进入后端目录：
   ```bash
   cd backend
   ```
2. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
3. 启动服务：
   ```bash
   uvicorn app.main:app --reload
   ```

## 目录结构

```
FinnewsHunter/
├── backend/            # FastAPI 后端服务
│   ├── app/            # 应用代码
│   └── tests/          # 测试用例
├── frontend/           # React 前端应用 (待初始化)
├── legacy_v1/          # 旧版代码归档
├── docs/               # 项目文档
└── README.md           # 项目说明
```