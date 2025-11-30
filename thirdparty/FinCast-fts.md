# FinCast-fts - Technical Deep Dive

## 1. Project Overview

FinCast is an open-source project that provides the official implementation of a novel **Foundation Model for Financial Time-Series Forecasting** [1]. The project's core purpose is to address the inherent challenges in financial forecasting, such as **temporal non-stationarity**, **multi-domain diversity**, and **varying temporal resolutions**, which often cause traditional deep learning models to overfit or require extensive, costly fine-tuning.

The model, also named FinCast, is a **decoder-only transformer** trained on an unprecedented scale of over **20 billion financial time points** [1]. This massive pre-training enables the model to capture a wide array of underlying financial patterns. A key feature is its robust **zero-shot performance**, meaning it can generate high-quality forecasts for new assets or markets without any additional training.

Main features include native support for **probabilistic forecasting** (outputting quantiles for risk assessment), a modular architecture incorporating a **Mixture-of-Experts (MoE)** layer for domain specialization, and the use of a custom **PQ-Loss** for joint optimization of point and probabilistic forecasts. The model is designed for high scalability, supporting up to 1 billion parameters with efficient inference. The target users are primarily financial researchers, quantitative analysts, and practitioners who require a state-of-the-art, generalizable, and risk-aware forecasting tool for diverse financial assets, including stocks, cryptocurrencies, and futures. The project is provided for research and educational purposes, with a clear disclaimer against using it for actual financial advice [2].

## 2. Architecture Design

FinCast is built upon a **decoder-only transformer** architecture, a design choice common in large language models but adapted here for time-series data [1]. The core component is the `PatchedTimeSeriesDecoder_MOE` (found in `src/ffm/pytorch_patched_decoder_MOE.py`), which extends the standard transformer decoder with two key innovations: **Mixture-of-Experts (MoE)** and a specialized loss function.

The overall system architecture is structured around the `FFmTorch` class, which inherits from `FFmBase` and provides the main forecasting API. This class handles checkpoint loading, device management (CPU/GPU), and the core `_forecast` logic. The model configuration is defined in `FFMConfig`, which specifies the architectural hyperparameters:
*   **Layers**: 50 transformer layers.
*   **Heads**: 16 attention heads.
*   **Hidden Size**: 1280 dimensions.
*   **Patching**: Input patch length of 32 and output patch length (horizon) of 128.

The **Mixture-of-Experts (MoE)** mechanism is a critical architectural feature, implemented using the `st_moe_pytorch` library. It allows the model to scale up to 1 billion parameters while enabling specialization across different financial domains. The MoE is configured with `num_experts` (e.g., 3) and `gating_top_n` (e.g., 2), meaning the model dynamically routes the input data to a subset of experts for processing, which significantly improves efficiency and capacity.

The model processes time-series data in patches, a technique that allows the transformer to operate on segments of the time series rather than individual points. The `ffm_base.py` module contains utility functions for data preparation, including normalization (`_normalize`), re-normalization (`_renormalize`), and handling time-series decomposition via moving averages. The `ffm_torch_moe.py` file orchestrates the inference process, preparing the input tensors (time series, padding, frequency) and feeding them into the `_model.decode` method for parallel processing and final output generation. This modular design separates the core model logic, the base API, and the data handling utilities, contributing to a clean and maintainable structure.

## 3. Core Technologies

FinCast leverages a modern stack of technologies centered around deep learning and high-performance computing.

*   **Programming Language**: **Python** (version 3.11+ recommended).
*   **Deep Learning Framework**: **PyTorch** (version 2.5+ recommended) is the primary framework for model implementation, training, and inference.
*   **Core Architecture**: **Decoder-only Transformer** architecture, adapted from large language models for time-series forecasting.
*   **Specialized Components**:
    *   **Mixture-of-Experts (MoE)**: A technique for scaling model capacity while maintaining computational efficiency, implemented using the `st_moe_pytorch` library.
    *   **PQ-Loss (Point + Quantile Loss)**: A custom loss function designed for joint point and probabilistic forecasting, which is crucial for financial risk assessment.
*   **Data Handling**: **NumPy** and **Pandas** are used extensively for time-series data manipulation, preprocessing, and feature engineering.
*   **Time-Series Utilities**: The project draws inspiration from and utilizes concepts from **TimesFM (Google Research)** and the `utilsforecast` library for time-series processing.
*   **Financial Data**: The `yfinance` library is used for accessing and retrieving financial market data.

## 4. Key Features

FinCast is distinguished by its foundation model approach and specialized components for financial time-series forecasting:

*   **Foundation Model for Financial Time-Series**: It is the first foundation model specifically engineered for financial data, trained on over 20 billion time points across diverse financial domains and temporal resolutions.
*   **Robust Zero-Shot Performance**: The model demonstrates strong generalization capabilities, allowing it to perform accurate forecasting on new, unseen financial time series without requiring domain-specific fine-tuning.
*   **Probabilistic Forecasting (Quantile Outputs)**: It natively supports the output of quantiles (e.g., 0.1, 0.5, 0.9), which is essential for quantifying forecast uncertainty and performing robust risk analysis in financial applications.
*   **PQ-Loss (Point + Quantile Loss)**: This custom loss function jointly optimizes for both the point forecast (mean/median) and the probabilistic forecast (quantiles), leading to more reliable and comprehensive predictions.
*   **Mixture-of-Experts (MoE) Architecture**: The MoE component allows the model to scale to a large number of parameters (up to 1 billion) while maintaining efficient inference by selectively activating only a subset of "expert" sub-networks based on the input data. This enables specialization across different financial domains (e.g., stocks vs. crypto).
*   **Flexible Context and Horizon**: The model supports flexible input context lengths and adjustable forecast horizons, making it highly adaptable to various forecasting tasks and time frames.
*   **PEFT Support**: The repository includes support for Parameter-Efficient Fine-Tuning (PEFT), such as LoRA/DORA, which allows users to fine-tune the massive model on custom datasets with minimal memory and computational overhead.

## 5. Technical Implementation Details

The technical implementation of FinCast is centered on adapting the transformer architecture for time-series data, focusing on scalability and probabilistic output.

### Code Structure

The repository is organized into a main source directory (`src`) with clear sub-modules:
*   `src/ffm`: Contains the core model logic (`ffm_torch_moe.py`, `ffm_base.py`, `pytorch_patched_decoder_MOE.py`) and time-series feature engineering (`time_features.py`).
*   `src/data_tools`: Houses data loading and sampling utilities (`TSdataset.py`, `batch_sampler.py`).
*   `src/st_moe_pytorch`: Includes the third-party implementation of the MoE layer.
*   `src/tools`: Provides utility functions for inference, metrics, and model handling.

### Agent Design and Data Flow

FinCast is not a multi-agent system but a single, powerful foundation model. The "agent" functionality is encapsulated within the `FFmTorch` class, which acts as the main API for forecasting.

1.  **Input Preparation**: The `_forecast` method in `ffm_torch_moe.py` receives a list of time series inputs. These are first preprocessed:
    *   They are truncated to the `context_len` (e.g., 512).
    *   Optional trend-residual decomposition is performed using a moving average (`ffm_base.moving_average`).
    *   The time series are normalized (`_normalize`) and padded to match the required input shape.
    *   Frequency information is encoded.
2.  **Model Execution**: The preprocessed data is batched and converted to PyTorch tensors, then passed to the `_model.decode` method. This is where the core **decoder-only transformer** with the **Mixture-of-Experts** layer processes the input. The MoE layer dynamically routes the input to a subset of experts, enabling specialized processing for different data segments.
3.  **Output Generation**: The model outputs two tensors: `mean_output` (the point forecast) and `full_output` (the full set of quantile forecasts).
4.  **Post-processing**: The outputs are re-normalized (`_renormalize`) using the statistics calculated during the input preparation phase. The final result is returned as NumPy arrays, ready for analysis.

### Implementation Specifics

The model's core is the `PatchedTimeSeriesDecoder_MOE` class, which is a patched version of a standard transformer decoder. The MoE layer is integrated into the feed-forward network (FFN) blocks of the transformer layers. The use of **patching** (e.g., `input_patch_len=32`) allows the model to capture long-range dependencies more effectively than point-wise models. The model is designed for **autoregressive decoding**, where the forecast is generated step-by-step, with each step predicting a patch of the time series. The `quantiles` attribute in `FFMConfig` (e.g., `[0.1, 0.2, ..., 0.9]`) directly influences the final output, ensuring the model is trained and configured to provide the necessary probabilistic forecasts. The implementation also includes logic to handle distributed training artifacts (e.g., stripping `_orig_mod.` from state dict keys) for seamless checkpoint loading.

## 6. Key Dependencies

The project relies on a focused set of Python libraries for its functionality, as listed in `requirement_v2.txt`:

*   **PyTorch**: The fundamental deep learning framework for the model.
*   **einops** and **einx**: Libraries for flexible and readable tensor operations, crucial for complex transformer and MoE architectures.
*   **st-moe-pytorch**: A specialized library for implementing the Mixture-of-Experts (MoE) component.
*   **huggingface-hub**: Used for model weight and dataset management, facilitating easy sharing and loading of the FinCast foundation model.
*   **numpy** and **pandas**: Essential for efficient numerical computation and time-series data manipulation.
*   **yfinance**: Used to fetch real-time and historical financial data for experimentation and inference.
*   **scikit-learn** and **scipy**: Provide general-purpose scientific computing and machine learning utilities.
*   **wandb**: Likely used for experiment tracking and visualization during the model training phase.
*   **peft**: Indicates support for Parameter-Efficient Fine-Tuning (PEFT), such as LoRA/DORA, to adapt the large foundation model to specific downstream tasks with minimal computational cost.

## 7. Use Cases

FinCast is designed to be a versatile tool for a wide range of financial time-series applications, leveraging its foundation model capabilities:

*   **Zero-Shot Forecasting for New Assets**: A quantitative analyst can use a pre-trained FinCast checkpoint to immediately generate forecasts for a newly listed stock, a novel cryptocurrency, or a commodity future without any fine-tuning. This is demonstrated by the repository's examples for Apple stock and Ethereum minute data [2].
*   **Probabilistic Risk Assessment**: Portfolio managers can utilize the native quantile outputs to assess the uncertainty and potential downside risk of their forecasts. For instance, the 0.1 and 0.9 quantiles can define a confidence interval for the price movement, aiding in setting stop-loss or take-profit orders.
*   **Cross-Domain Pattern Transfer**: Researchers can leverage the MoE-enabled domain specialization to transfer knowledge learned from high-frequency stock data to lower-frequency macroeconomic indicators, improving forecast accuracy where data is sparse.
*   **Parameter-Efficient Fine-Tuning (PEFT)**: A financial institution can use PEFT techniques (like LoRA, which is supported) to quickly and cheaply adapt the massive FinCast model to their proprietary, internal datasets (e.g., internal trading volumes or credit default swap spreads) without retraining the entire model.
*   **Long-Horizon Forecasting**: The model's design, with a large `horizon_len` (e.g., 128), makes it suitable for strategic planning and long-term market outlooks, going beyond the short-term predictions of traditional models.

## 8. Strengths & Limitations

**Strengths**

The primary strength of FinCast lies in its **foundation model paradigm**, which enables **robust zero-shot performance** across diverse financial domains and frequencies, significantly reducing the need for domain-specific fine-tuning [1]. The **Mixture-of-Experts (MoE)** architecture is a major technical advantage, allowing the model to scale its capacity (up to 1 billion parameters) for better pattern recognition while maintaining **efficient inference** by only activating a subset of experts. This addresses the trade-off between model size and computational cost. Furthermore, the native support for **probabilistic forecasting** via quantile outputs and the specialized **PQ-Loss** make it highly valuable for financial risk management, providing a measure of uncertainty alongside the point forecast. The modular design, built on PyTorch and drawing inspiration from established models like TimesFM, ensures a clean, extensible, and high-performance codebase.

**Limitations**

As a large foundation model, FinCast has a significant **computational footprint** for initial pre-training, which is a barrier to entry for most users. While inference is efficient due to MoE, the model still requires substantial resources (e.g., GPU) compared to simpler time-series models. The project's disclaimer explicitly states it is for **research and educational purposes only** and does not constitute financial advice, highlighting the inherent risks and limitations of applying any model to the highly non-stationary and chaotic financial markets [2]. Finally, the reliance on a patched decoder and the MoE implementation from external, specialized libraries (`st_moe_pytorch`) introduces a dependency on the maintenance and stability of those third-party components.

## 9. GitHub Repository

[https://github.com/vincent05r/FinCast-fts](https://github.com/vincent05r/FinCast-fts)
