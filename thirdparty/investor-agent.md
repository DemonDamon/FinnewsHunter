# investor-agent - Technical Deep Dive

## 1. Project Overview

The **investor-agent** is an open-source project designed as a specialized **Model Context Protocol (MCP) server** to provide Large Language Models (LLMs) with comprehensive, structured financial data and analysis capabilities. Its primary purpose is to act as a reliable, real-time financial data oracle, enabling LLMs to perform sophisticated investment research, market analysis, and financial reporting.

The agent aggregates data from multiple sources, primarily leveraging the `yfinance` library for core financial data, supplemented by direct API calls to sources like Nasdaq and CNN for specialized information such as earnings calendars and market sentiment indices. A key design principle is resilience, achieved through a multi-layered caching and retry mechanism to handle API rate limits and transient network errors effectively.

The main features include fetching market movers, detailed ticker information, historical price data, financial statements, ownership analysis, and calculating technical indicators. The agent's output is meticulously formatted into clean CSV strings, making the data highly structured and easily parsable by the consuming LLM. The target users are developers, data scientists, and financial analysts who utilize LLMs (such as those integrated with the MCP) for automated financial research and decision-making. The project's modular design, with optional dependencies for technical analysis and high-frequency data, allows for flexible deployment tailored to specific analytical requirements.

## 2. Architecture Design

The **investor-agent** is designed as a **Model Context Protocol (MCP) server**, which is a specialized architecture for exposing financial data and analysis tools to Large Language Models (LLMs). The core of the architecture is the `FastMCP` class from the `mcp` library, which handles the server setup and tool registration.

The system operates on a **client-server model** where the LLM acts as the client, invoking the agent's functions (tools) via the MCP.

**Key Architectural Components:**

1.  **FastMCP Server (`investor_agent.server:mcp`)**: This is the central component that initializes the agent and registers all financial analysis functions as callable tools. It provides the necessary interface for LLMs to interact with the agent.
2.  **Data Acquisition Layer**: This layer is responsible for fetching raw financial data from various external sources. The primary data source is **Yahoo Finance**, accessed via the `yfinance` library. Other sources include the **Nasdaq API** for earnings, **CNN** for the Fear & Greed Index, and **alternative.me** for the Crypto Fear & Greed Index.
3.  **Data Processing and Transformation Layer**: This layer uses the **Pandas** library extensively to process, clean, and transform the raw data into structured formats, primarily **CSV strings**, which are highly suitable for LLM consumption. Utility functions like `to_clean_csv` ensure consistent output.
4.  **Resilience and Caching Layer**: A multi-layered strategy ensures robustness:
    *   **`yfinance[nospam]`**: Provides built-in smart caching and rate limiting for Yahoo Finance API calls.
    *   **`hishel`**: An HTTP response caching library used for external API calls (e.g., CNN, Crypto) to minimize redundant requests and respect rate limits.
    *   **`tenacity`**: Implements a robust retry logic with exponential backoff for transient failures (e.g., rate limits, 5xx errors) in both `yfinance` and generic HTTP calls.
5.  **Optional Modules**: The architecture supports modular extensions for specialized tasks:
    *   **Technical Analysis (TA)**: If the `ta-lib` C library and Python wrapper are installed, the `calculate_technical_indicator` tool is registered, enabling advanced technical analysis.
    *   **Intraday Data**: If the `alpaca-py` library is installed and API keys are configured, the `fetch_intraday_data` tool is registered, providing access to 15-minute historical stock bars via the Alpaca API.

The system leverages **`concurrent.futures.ThreadPoolExecutor`** for parallel execution of multiple data fetching tasks (e.g., fetching basic info, calendar, and news for a ticker simultaneously), significantly improving performance. The overall design is a highly resilient, data-centric microservice optimized for providing structured financial data to an LLM-driven workflow.

## 3. Core Technologies

The project is built primarily on **Python 3.12+** and leverages a set of powerful libraries for financial data processing and agent communication.

*   **Programming Language**: **Python 3.12+**.
*   **Agent Framework**: **Model Context Protocol (MCP)**, implemented via the `mcp` library's `FastMCP` server. This is the core communication layer for the agent.
*   **Primary Data Source**: **`yfinance[nospam]`** (a fork of `yfinance`) for comprehensive market data, including quotes, history, financial statements, and ownership data.
*   **Data Manipulation**: **`pandas`** is fundamental for all data processing, cleaning, and transformation tasks, especially converting raw data into LLM-friendly CSV strings.
*   **Web Scraping/APIs**:
    *   **`httpx`** and **`hishel`** for asynchronous HTTP requests and caching, used for external APIs like CNN and Nasdaq.
    *   **`pytrends`** for fetching Google Trends data as a market sentiment indicator.
*   **Resilience and Error Handling**:
    *   **`tenacity`** for implementing retry logic with exponential backoff to handle transient network errors and API rate limits.
*   **Optional Technologies**:
    *   **`ta-lib`** (via Python wrapper) for advanced technical indicators (SMA, EMA, RSI, MACD, BBANDS).
    *   **`alpaca-py`** for accessing 15-minute intraday stock bars via the Alpaca Markets API.
*   **Concurrency**: **`concurrent.futures.ThreadPoolExecutor`** is used to parallelize multiple data fetching calls to `yfinance`, improving response time for complex queries.

## 4. Key Features

The **investor-agent** provides a comprehensive suite of financial analysis tools exposed as callable functions for LLMs:

*   **Comprehensive Ticker Analysis**: A single tool (`get_ticker_data`) consolidates essential company information, news, analyst recommendations, and upgrades/downgrades, with configurable limits for each section.
*   **Market Movers and Sentiment**: Tools to fetch real-time market movers (gainers, losers, most-active) and key sentiment indicators, including the **CNN Fear & Greed Index**, **Crypto Fear & Greed Index**, and **Google Trends** search interest.
*   **Smart Data Optimization**: The agent employs a "smart interval selection" for historical data (`get_price_history`), using daily intervals for shorter periods (≤1y) and monthly intervals for longer periods (≥2y) to optimize data volume and LLM context size.
*   **Parallel Data Fetching**: Utilizes `ThreadPoolExecutor` to fetch multiple data points (e.g., financial statements, holder data) concurrently, significantly reducing latency.
*   **Robust Data Resilience**: Implements a multi-layered caching and retry strategy using `yfinance[nospam]`, `hishel`, and `tenacity` to ensure high availability and compliance with API rate limits.
*   **Modular Extensibility**: Supports optional installation of **TA-Lib** for advanced technical analysis and **Alpaca-py** for high-resolution intraday data, allowing users to customize the agent's capabilities based on their needs.
*   **LLM-Optimized Output**: All complex data structures (DataFrames) are consistently converted into clean, index-less **CSV strings** using the `to_clean_csv` utility, making the output directly consumable and interpretable by LLMs.

## 5. Technical Implementation Details

The technical implementation is centered around the `investor_agent/server.py` file, which defines the MCP server and all its callable tools.

**Data Flow and Processing Pipeline**

The data flow is initiated by an LLM client invoking a registered tool (e.g., `get_ticker_data`).

1.  **Tool Invocation**: The `FastMCP` server receives the request and calls the corresponding Python function.
2.  **Data Fetching**: Functions like `get_ticker_data` use `concurrent.futures.ThreadPoolExecutor` to parallelize calls to the underlying data sources, primarily the `yf_call` wrapper for `yfinance`. For external APIs (CNN, Nasdaq), the `fetch_json` or `fetch_text` asynchronous functions are used, which are wrapped with the `@api_retry` decorator and utilize the `hishel` cached `AsyncCacheClient`.
3.  **Data Transformation**: The raw data, often returned as Pandas DataFrames or nested dictionaries, is processed. For DataFrames, the utility function `to_clean_csv(df: pd.DataFrame) -> str` is crucial. This function cleans the DataFrame by removing empty columns and converts it into a clean, index-less CSV string, ensuring the output is LLM-friendly.

**Agent Design**

The **investor-agent** is a single, specialized agent following the **Tool-Use Agent** pattern. It does not employ a multi-agent system but rather acts as a single, highly capable tool provider. The agent's "intelligence" is in its ability to:
*   **Validate Inputs**: Functions like `validate_ticker` and `validate_date` ensure data integrity before API calls.
*   **Select Optimal Data**: The `get_price_history` function demonstrates logic for selecting the appropriate interval ("1d" or "1mo") based on the requested period to manage data volume.
*   **Handle Failures**: The extensive use of `tenacity` for retries is a core part of the agent's robust design.

**Code Structure**

The project has a minimal and clean structure:

```
investor-agent-project/
├── investor_agent/
│   ├── __init__.py
│   └── server.py  # Core logic, MCP server, and all tool definitions
├── chat.py        # Local testing script for development
├── pyproject.toml # Project metadata and dependencies
└── README.md      # Documentation
```

The core logic is entirely contained within `investor_agent/server.py`. The `pyproject.toml` defines the entry point: `investor-agent = "investor_agent.server:mcp.run"`, which executes the `FastMCP` server.

**Implementation Specifics (Example: `get_ticker_data`)**

The `get_ticker_data` function showcases the parallel execution pattern:

```python
with ThreadPoolExecutor() as executor:
    info_future = executor.submit(yf_call, ticker, "get_info")
    calendar_future = executor.submit(yf_call, ticker, "get_calendar")
    news_future = executor.submit(yf_call, ticker, "get_news")
    # ... retrieve results ...
```

This pattern allows the agent to fetch multiple distinct pieces of information from `yfinance` concurrently, which is a significant performance optimization. The subsequent processing then transforms these results into a unified JSON object containing multiple structured lists and CSV strings.

**Implementation Specifics (Example: `calculate_technical_indicator`)**

The technical analysis tool is conditionally registered based on the availability of `ta-lib`. It fetches historical data, uses `talib` functions (e.g., `talib.RSI`, `talib.MACD`) on the closing prices, and then aligns the resulting indicator series with the original price data before converting both to separate CSV strings for the LLM. This separation of price and indicator data ensures clarity and modularity in the output.

## 6. Key Dependencies

The project relies on a focused set of dependencies, categorized by their primary function:

*   **Core Functionality**:
    *   **`mcp[cli]`**: Provides the Model Context Protocol (MCP) server implementation, enabling the agent to communicate with LLM clients.
    *   **`yfinance[nospam]`**: The primary library for fetching financial data from Yahoo Finance.
    *   **`pandas`**: Essential for data manipulation, cleaning, and conversion to CSV format.
*   **Resilience and Networking**:
    *   **`hishel`**: Used for HTTP response caching to reduce external API calls and manage rate limits.
    *   **`httpx`**: An asynchronous HTTP client used for fetching data from various web sources (e.g., CNN, Nasdaq).
    *   **`tenacity`**: Implements a robust retry mechanism for API calls, enhancing the agent's reliability against transient failures.
*   **Specialized Data**:
    *   **`pytrends`**: Used to retrieve Google Trends data for market sentiment analysis.
    *   **`anysqlite`**: Likely used by `hishel` for persistent storage of the HTTP cache.
*   **Optional Dependencies**:
    *   **`ta-lib`**: Required for the `ta` optional group to enable technical indicator calculations.
    *   **`alpaca-py`**: Required for the `alpaca` optional group to fetch intraday data from Alpaca Markets.

## 7. Use Cases

The **investor-agent** is designed for a variety of automated financial analysis and research scenarios, particularly those involving LLMs:

*   **Automated Investment Research**: An LLM can be tasked with generating a comprehensive research report on a stock (e.g., "Analyze Apple's financial health and market sentiment"). The LLM would sequentially call `get_ticker_data`, `get_financial_statements`, and `get_institutional_holders` to gather all necessary data points, then synthesize the final report.
*   **Market Monitoring and Alerting**: The agent can be used to power a daily market summary. An LLM could call `get_market_movers` to identify top gainers and losers, and `get_cnn_fear_greed_index` to gauge overall market sentiment, generating a concise morning brief.
*   **Quantitative Strategy Backtesting**: While not a full backtesting engine, the agent provides the necessary data. A quantitative LLM could use `get_price_history` and `calculate_technical_indicator` to retrieve time-series data and technical signals, which can then be fed into a separate backtesting script or analyzed directly by the LLM for pattern recognition.
*   **Earnings Calendar Tracking**: Developers can build applications that use `get_nasdaq_earnings_calendar` to track upcoming earnings announcements for a portfolio of stocks, enabling proactive trading or research decisions ahead of key events.
*   **Options Strategy Generation**: An LLM can use the highly filtered output of `get_options` to identify specific options contracts (e.g., calls with a strike price below the current stock price and high open interest) to recommend complex options strategies.

## 8. Strengths & Limitations

**Strengths**

The primary strength of the **investor-agent** lies in its **robustness and resilience** against common API limitations. The multi-layered caching (`yfinance[nospam]`, `hishel`) and retry (`tenacity`) strategy ensures high reliability and minimizes the risk of rate-limiting issues, which are common when scraping public financial data sources. Its architecture as an **MCP server** makes it natively compatible with LLM-driven workflows, providing a structured, tool-based interface that is superior to simple text-based data retrieval. The extensive use of **Pandas** for data processing and the consistent output of **clean CSV strings** ensure that the data delivered to the LLM is highly structured, unambiguous, and ready for immediate analysis. Furthermore, the use of **`ThreadPoolExecutor`** for parallel data fetching significantly reduces latency for complex, multi-source queries. The modular design with optional dependencies for **TA-Lib** and **Alpaca-py** allows for a lean core installation while providing a clear path for feature expansion.

**Limitations**

The main limitation is the heavy reliance on **Yahoo Finance** as the primary data source, which may be subject to data quality issues, unexpected API changes, or service interruptions outside the project's control. The optional technical analysis feature requires the installation of the **TA-Lib C library**, which can be a complex prerequisite for some users, particularly on non-Linux operating systems. While the agent is highly effective at retrieving and structuring data, it does not include any built-in LLM for interpretation or decision-making; it is purely a data provider. Finally, the use of web scraping techniques for market movers and sentiment indices (e.g., CNN Fear & Greed) makes these specific tools vulnerable to changes in the source website's HTML structure.

## 9. GitHub Repository

[https://github.com/ferdousbhai/investor-agent](https://github.com/ferdousbhai/investor-agent)
