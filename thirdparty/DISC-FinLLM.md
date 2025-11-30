# DISC-FinLLM - In-Depth Source Code Analysis

## Phase 1: Global Scan & Planning

### 1.1. Full Directory Structure

```
```
/home/ubuntu/DISC-FinLLM
|-- .git/ (Git version control metadata)
|-- LICENSE (Project license)
|-- README-en.md (English documentation and project overview)
|-- README.md (Chinese documentation and project overview)
|-- cli_demo.py (Command-line interface demonstration and entry point)
|-- web_demo.py (Web interface demonstration and entry point)
|-- requirements.txt (Python package dependencies)
|-- data/ (Contains JSON data files for different model components)
|   |-- README.md
|   |-- computing_part.json (Data for the financial computing module)
|   |-- consulting_part.json (Data for the financial consulting module)
|   |-- retrieval_part.json (Data for the financial knowledge retrieval module)
|   |-- task_part.json (Data for the financial text analysis module)
|-- eval/ (Contains evaluation data and the core evaluation logic)
|   |-- README.md
|   |-- computing_eval.json (Evaluation data for the computing module)
|   |-- retriever_eval.json (Evaluation data for the retrieval module)
|   |-- evaluator/ (Core module for all evaluation logic)
|       |-- README.md
|       |-- autoeval.py (Script for automated evaluation)
|       |-- evaluate.py (Main evaluation script)
|       |-- finllm.py (Core class/functions for interacting with the FinLLM)
|       |-- preprocess.py (Script for data preprocessing before evaluation)
|       |-- utils.py (Utility functions for evaluation)
|-- images/ (Contains images used in the documentation)
|   |-- README.md
|   |-- data_en.png
|   |-- data_zh.png
|   |-- example_consult.gif
|   |-- example_retrieval.gif
|   |-- example_task.gif
|   |-- example_tool.gif
|   |-- lora_en.png
|   |-- lora_zh.png
|   |-- model_en.png
|   |-- model_zh.png
```

The project structure is concise and clearly organized, primarily focusing on demonstration, data, and evaluation. The root directory contains the main entry points (`cli_demo.py`, `web_demo.py`) and configuration files. The `data/` directory holds the instruction-tuning data for the four expert modules: financial consulting, text analysis, computing, and knowledge retrieval. The `eval/` directory is dedicated to model assessment, with the critical `evaluator/` subdirectory housing the core Python logic for evaluating the model's performance across different tasks. The `images/` folder contains visual assets for the documentation. This clean separation of concerns facilitates easy navigation and maintenance.
```

### 1.2. Core Folders for Analysis

*   `/home/ubuntu/DISC-FinLLM`: Contains the main application entry points (`cli_demo.py`, `web_demo.py`) that demonstrate the model's capabilities and orchestrate the high-level flow.
*   `/home/ubuntu/DISC-FinLLM/eval/evaluator`: Contains the core Python classes and functions (`finllm.py`, `evaluate.py`, `autoeval.py`, `preprocess.py`, `utils.py`) responsible for loading the model, running evaluations, and handling data preparation. This is the heart of the model's operational and assessment logic.

## Phase 2: Module-by-Module Deep Analysis

## Module 1: Root/Demo Module (`/home/ubuntu/DISC-FinLLM`)

### Core Responsibility
This module serves as the primary interface layer for the DISC-FinLLM, providing two distinct demonstration entry points: a command-line interface (`cli_demo.py`) and a web-based interface (`web_demo.py`). Its core function is to load the pre-trained FinLLM model and tokenizer, manage the conversation history, and facilitate real-time interaction with the user, including support for streaming responses.

### Key Files and Functions
*   **`cli_demo.py`**: Provides a simple, interactive terminal chat interface.
    *   `init_model()`: Loads the model and tokenizer from the "Go4miii/DISC-FinLLM" path using `AutoModelForCausalLM` and `AutoTokenizer` from the `transformers` library. It sets `torch_dtype=torch.float16` and `device_map="auto"` for efficient loading.
    *   `clear_screen()`: Handles terminal clearing and prints the welcome message in Chinese, defining the basic commands (`exit`, `clear`, `stream`).
    *   `main()`: The main chat loop, handling user input, command parsing, and calling the model's `chat` method for response generation, with optional streaming.
*   **`web_demo.py`**: Implements a graphical chat interface using the `streamlit` framework.
    *   `init_model()`: Similar to the CLI version, but decorated with `@st.cache_resource` to ensure the large model is loaded only once across sessions.
    *   `clear_chat_history()`: Clears the `st.session_state.messages`.
    *   `init_chat_history()`: Initializes the chat history and displays previous messages in the Streamlit interface.
    *   `main()`: The main web application logic, handling user input via `st.chat_input` and displaying the model's streaming response in a chat message container.

### Core Implementation and Dependencies
The core implementation relies heavily on the **Hugging Face `transformers`** library. The model loading process is standardized:
1.  Load the model: `AutoModelForCausalLM.from_pretrained(...)`
2.  Load the tokenizer: `AutoTokenizer.from_pretrained(...)`
3.  Load generation configuration: `GenerationConfig.from_pretrained(...)`

The key interaction is the custom `model.chat(tokenizer, messages, stream=True)` method, which is assumed to be implemented within the model's `trust_remote_code` or a custom wrapper, providing a clean, multi-turn chat API.

**Dependencies**: `torch`, `transformers`, `colorama` (for CLI), `streamlit` (for Web).

## Module 2: Evaluation/Core Logic Module (`/home/ubuntu/DISC-FinLLM/eval/evaluator`)

### Core Responsibility
This module contains the comprehensive framework for evaluating the performance of the DISC-FinLLM and other comparable models on the BBT-FinCUGE financial NLP benchmark. It abstracts the LLM interaction, manages model-specific configurations, handles dataset preprocessing, and implements task-specific evaluation metrics.

### Key Files and Functions
*   **`finllm.py`**: **LLM Abstraction and Model Wrappers**.
    *   `DISCFINLLMBase` (Abstract Base Class): Defines the contract for all LLM wrappers with an abstract `generate(self, prompt: str) -> str` method.
    *   Concrete Classes: Implements wrappers for various models like `DISCVFINLLMChatGLM26B`, `DISCVFINLLMBaichuan13BChat`, etc. These classes handle model-specific loading (including **LoRA** fine-tuning via `peft.PeftModel`), tokenization, and the actual generation call.
*   **`evaluate.py`**: **Evaluation Logic and Prompt Engineering**.
    *   Multiple `*Evaluator` Classes (e.g., `FinFEEvaluator`, `FinQAEvaluator`): Each class is responsible for a specific financial task (e.g., sentiment analysis, QA).
    *   `__init__`: Loads the task-specific evaluation data and few-shot instruction samples.
    *   `build_zero_shot_prompt` / `build_few_shot_prompt`: Implements prompt engineering by constructing the input text based on predefined templates and few-shot examples.
    *   `evaluate`: Calculates the final metric (e.g., accuracy for sentiment, F1 for QA) by comparing model predictions (`preds`) with ground truth (`golds`).
    *   `run_evaluation`: The main evaluation loop, iterating over all data samples, generating responses using the injected `llm.generate()` method, and calculating both zero-shot and few-shot metrics.
*   **`autoeval.py`**: **Evaluation Orchestration**.
    *   `model_lists` and `Eval_datasets`: Dictionaries mapping string names to the respective model and evaluator classes, implementing a **Factory Pattern**.
    *   `main` block: Parses command-line arguments for model name, LoRA path, and dataset. It instantiates the chosen `llm` and `evaluator` and calls `evaluator().run_evaluation(llm)`.
*   **`preprocess.py`**: **Data Preparation**.
    *   `BBTFinCUGE` class: Manages the downloading and processing of the raw BBT-FinCUGE datasets.
    *   `download_all()`: Uses `requests` to fetch raw JSON data from a GitHub repository.
    *   `process_*` methods (e.g., `process_finfe`): Converts the raw dataset format into a standardized list of instances with `id`, `input`, `gold_answer`, and `source` fields.
*   **`utils.py`**: **Utility Functions**.
    *   `write_json`, `load_json`: Standardized JSON file I/O.
    *   `_mixed_segmentation`, `_remove_punctuation`: Text cleaning and tokenization utilities, crucial for Chinese NLP tasks, using `nltk.word_tokenize`.
    *   `_find_lcs`, `_compute_f1_score`: Implements the Longest Common Subsequence (LCS) algorithm and F1 score calculation, which is the core metric for generative tasks like QA.

### Dependencies and Error/Performance
**Dependencies**: `transformers`, `peft`, `torch`, `argparse`, `tqdm`, `requests`, `inspect`, `random`, `nltk`.
**Performance**: The use of `torch.float16` and `device_map="auto"` in model loading across all modules is a key performance optimization for large models on GPU. The `tqdm` library is used in `evaluate.py` to provide progress bars, enhancing user experience during long evaluation runs.
**Error Handling**: Basic file existence checks are present in `preprocess.py` (`if not os.path.exists(file_path)`). The `evaluate.py` includes assertions (`assert len(golds) == len(preds)`) to ensure data integrity before metric calculation.

### Module PlantUML Diagrams

### Module 1: Root/Demo Module

```plantuml
@startuml
title Root/Demo Module (cli_demo.py & web_demo.py)

class AutoModelForCausalLM
class AutoTokenizer
class GenerationConfig
class torch
class streamlit as st
class colorama

package "Demo Scripts" {
    class cli_demo {
        + init_model()
        + clear_screen()
        + main()
    }

    class web_demo {
        + @st.cache_resource init_model()
        + clear_chat_history()
        + init_chat_history()
        + main()
    }
}

cli_demo ..> AutoModelForCausalLM : loads
cli_demo ..> AutoTokenizer : loads
cli_demo ..> GenerationConfig : loads
cli_demo ..> torch : uses
cli_demo ..> colorama : uses

web_demo ..> AutoModelForCausalLM : loads
web_demo ..> AutoTokenizer : loads
web_demo ..> GenerationConfig : loads
web_demo ..> torch : uses
web_demo ..> st : uses

AutoModelForCausalLM <.. cli_demo : model.chat()
AutoModelForCausalLM <.. web_demo : model.chat()

@enduml
```

### Module 2: Evaluation/Core Logic Module

```plantuml
@startuml
title Evaluation/Core Logic Module (eval/evaluator)

abstract class DISCFINLLMBase {
    + generate(prompt: str): str {abstract}
}

package "LLM Wrappers (finllm.py)" {
    class DISCVFINLLMChatGLM26B
    class DISCVFINLLMBaichuan13BChat
    class FinGPTv3
    DISCFINLLMBase <|-- DISCVFINLLMChatGLM26B
    DISCFINLLMBase <|-- DISCVFINLLMBaichuan13BChat
    DISCFINLLMBase <|-- FinGPTv3
}

package "Data Preprocessing (preprocess.py)" {
    class BBTFinCUGE {
        + download_all()
        + process_finfe()
        + process_finqa()
        .. other process methods ..
    }
}

package "Evaluation Logic (evaluate.py)" {
    class FinFEEvaluator {
        + build_zero_shot_prompt()
        + build_few_shot_prompt()
        + evaluate(golds, preds)
        + run_evaluation(llm)
    }
    class FinQAEvaluator
    class FinCQAEvaluator
    .. other Evaluators ..

    FinFEEvaluator ..> BBTFinCUGE : loads instruct samples
    FinFEEvaluator ..> DISCFINLLMBase : calls generate()
}

package "Utilities (utils.py)" {
    class Utils {
        + write_json()
        + load_json()
        + _mixed_segmentation()
        + _find_lcs()
        + _compute_f1_score()
    }
}

package "Orchestration (autoeval.py)" {
    class AutoEval {
        + model_lists
        + Eval_datasets
        + main()
    }
}

AutoEval --> DISCFINLLMBase : instantiates model
AutoEval --> FinFEEvaluator : instantiates evaluator
FinFEEvaluator ..> Utils : uses metrics/text processing
BBTFinCUGE ..> Utils : uses load/write_json

@enduml
```

## Phase 3: Overall Architecture & Summary

### 3.1. Overall Architecture Analysis

#### 3.1.1. Core Abstractions

The DISC-FinLLM project is structured around a **modular, multi-expert design philosophy** centered on a clear separation of concerns between the LLM interaction, task-specific evaluation, and application demonstration.

The **core abstraction** is the `DISCFINLLMBase` abstract class defined in `finllm.py`. This class establishes a standardized interface (`generate(prompt: str) -> str`) for all underlying Large Language Models (LLMs), effectively decoupling the evaluation and application logic from the specific model implementation (e.g., ChatGLM, Baichuan, Bloomz). This allows the system to be easily extended to support new base models or different fine-tuned versions without modifying the evaluation framework.

The **design philosophy** is a **"Model-as-a-Service"** approach within the evaluation context. The LLM is treated as a black-box component that accepts a prompt and returns a response. The complexity of model loading, LoRA weight merging, and device management is encapsulated within the concrete model wrapper classes (e.g., `DISCVFINLLMBaichuan13BChat`). This encapsulation promotes code reusability and maintainability. Furthermore, the project implicitly follows a **Multi-Expert System** design, where the four data files (`consulting_part.json`, `task_part.json`, etc.) suggest the model is fine-tuned for distinct financial sub-tasks, which is then validated by the corresponding task-specific evaluators in `evaluate.py`.

The **lifecycle management** of the application is straightforward:
1.  **Data Preparation**: The `preprocess.py` script manages the initial lifecycle phase by downloading and transforming raw BBT-FinCUGE data into a standardized format for evaluation.
2.  **Model Loading**: The model is loaded once at the start of the application, either via `init_model()` in the demo scripts or via the `autoeval.py` orchestrator. Crucially, the use of `torch.float16` and `device_map="auto"` ensures efficient, memory-optimized loading onto available hardware.
3.  **Execution**:
    *   **Demo Lifecycle**: The demo scripts maintain a continuous loop, managing conversation history (`messages` list) and repeatedly calling the model's `chat` method for each user turn.
    *   **Evaluation Lifecycle**: The `autoeval.py` script orchestrates the evaluation, instantiating the chosen model and evaluator, running the full `run_evaluation` loop, and finally writing the metrics to a JSON file.

#### 3.1.2. Component Interactions

The project exhibits two primary interaction flows: the **Demonstration Flow** and the **Evaluation Flow**.

## 1. Demonstration Flow (e.g., `cli_demo.py`)
This flow is a direct, synchronous interaction between the user interface and the LLM.
1.  **Initialization**: `cli_demo.py` calls `init_model()` to load the model and tokenizer.
2.  **User Input**: The user provides a `prompt`.
3.  **Request**: The script appends the user's prompt to the `messages` history.
4.  **Generation**: The script calls the model's custom `model.chat(tokenizer, messages, stream=True)` method.
5.  **Response**: The model generates a response, which is either printed as a stream (in `cli_demo.py`) or updated in a placeholder (in `web_demo.py`).
6.  **History Update**: The model's response is appended to the `messages` history, maintaining the conversational context.

## 2. Evaluation Flow (`autoeval.py` Orchestration)
This flow is more complex, involving multiple components to systematically test the LLM.
1.  **Orchestration**: `autoeval.py` instantiates a specific `DISCFINLLMBase` implementation (`llm`) and one or more `*Evaluator` instances.
2.  **Data Access**: The `*Evaluator` (e.g., `FinFEEvaluator`) loads its task-specific evaluation data (`finfe-eval.jsonl`) and few-shot samples (`instruct_samples.json`) using helper functions from `utils.py`.
3.  **Prompt Engineering**: Inside `*Evaluator.run_evaluation()`, for each data sample, the appropriate prompt construction method (`build_zero_shot_prompt` or `build_few_shot_prompt`) is called. This is where the task-specific instruction and context are formatted for the LLM.
4.  **LLM Interaction**: The evaluator calls `llm.generate(input_text)` on the model wrapper. This is the critical communication point, abstracting the underlying model's API.
5.  **Metric Calculation**: The evaluator collects the model's predictions (`preds`) and compares them to the ground truth (`golds`). It uses utility functions from `utils.py` (e.g., `_remove_punctuation`, `_find_lcs`) to clean text and calculate metrics like F1 score or accuracy.
6.  **Result Reporting**: The final metrics are returned to `autoeval.py`, which then aggregates and writes the results to a JSON file using `utils.write_json`.

The communication pattern between the `*Evaluator` and the `DISCFINLLMBase` is a clear example of the **Strategy Pattern**, where the evaluation logic (context) uses the model wrapper (strategy) to perform the generation task.

### 3.2. Overall Architecture PlantUML Diagram

```plantuml
@startuml
@startuml
title DISC-FinLLM Overall Architecture

skinparam componentStyle rectangle

package "Application Layer" {
    [cli_demo.py] as CLI
    [web_demo.py] as WEB
}

package "Core Model Abstraction" {
    abstract class DISCFINLLMBase
    [Model Wrappers (finllm.py)] as WRAPPER
    DISCFINLLMBase <|-- WRAPPER
}

package "Evaluation Framework" {
    [autoeval.py] as ORCHESTRATOR
    [evaluate.py] as EVAL_LOGIC
    [preprocess.py] as PREPROCESS
    [utils.py] as UTILS
    [Task Evaluators (e.g., FinFEEvaluator)] as EVALUATOR
    EVAL_LOGIC ..> EVALUATOR
}

package "External Dependencies" {
    [Hugging Face Transformers] as HF
    [PEFT (LoRA)] as PEFT
    [BBT-FinCUGE Data] as DATA
}

CLI --> WRAPPER : loads & interacts
WEB --> WRAPPER : loads & interacts

ORCHESTRATOR --> WRAPPER : instantiates LLM
ORCHESTRATOR --> EVALUATOR : instantiates Task Logic

EVALUATOR --> WRAPPER : calls generate()
EVALUATOR --> UTILS : uses metrics/helpers
PREPROCESS --> DATA : downloads
PREPROCESS --> UTILS : uses I/O

WRAPPER --> HF : uses AutoModel/Tokenizer
WRAPPER --> PEFT : loads LoRA weights

@enduml
@enduml
```

### 3.3. Design Patterns & Highlights

#### 3.3.1. Design Patterns

The codebase, particularly the evaluation framework, leverages several fundamental design patterns to manage complexity and promote extensibility.

## 1. Factory Pattern (Simple Factory)
*   **Description**: The Factory Pattern is used to create objects without exposing the instantiation logic to the client.
*   **Implementation**: In `autoeval.py`, the dictionaries `model_lists` and `Eval_datasets` act as simple factories.
*   **Code Example (`autoeval.py`):**
    ```python
    # Factory for LLM models
    model_lists = {
        'chatglm-6b': DISCVFINLLMChatGLM6B,
        'baichuan-13b-chat': DISCVFINLLMBaichuan13BChat,
        # ...
    }
    # Factory for Evaluators
    Eval_datasets = {
        'finfe': FinFEEvaluator,
        'finqa': FinQAEvaluator,
        # ...
    }
    # Client code instantiates based on string key
    llm = model_lists.get(model_name)(device, lora_path)
    # ...
    evaluator = Eval_datasets.get(eval_data)
    ```

## 2. Abstract Factory / Template Method Pattern
*   **Description**: The Abstract Factory pattern provides an interface for creating families of related or dependent objects without specifying their concrete classes. The Template Method pattern defines the skeleton of an algorithm in the superclass but lets subclasses override specific steps.
*   **Implementation**: The `DISCFINLLMBase` abstract class defines the common interface (`generate`), while each concrete model wrapper (e.g., `DISCVFINLLMBaichuan13BChat`) implements the specific steps for model loading, tokenization, and generation logic, which varies significantly between models (e.g., ChatGLM's `chat` method vs. Baichuan's prompt templating).

## 3. Strategy Pattern
*   **Description**: The Strategy Pattern defines a family of algorithms, encapsulates each one, and makes them interchangeable.
*   **Implementation**: The `*Evaluator` classes (the context) use the `DISCFINLLMBase` instance (`llm`, the strategy) to perform the text generation. The evaluation logic remains the same regardless of which concrete LLM implementation is used.

#### 3.3.2. Project Highlights

The DISC-FinLLM project demonstrates several key design strengths, primarily focused on rigorous evaluation and model flexibility.

*   **Comprehensive Evaluation Framework**: The most significant highlight is the dedicated, multi-task evaluation framework. By integrating the BBT-FinCUGE benchmark and creating distinct `*Evaluator` classes for tasks like sentiment analysis (`FinFE`), question answering (`FinQA`), and relation extraction (`FinRE`), the project ensures a **systematic and reproducible assessment** of the LLM's performance across the financial domain.
*   **Model Agnosticism via Abstraction**: The use of the `DISCFINLLMBase` abstract class provides excellent **extensibility**. New LLMs (e.g., Llama, Qwen) can be integrated simply by creating a new concrete wrapper class that implements the `generate` method, without altering the core evaluation or demonstration logic.
*   **LoRA Fine-Tuning Support**: The model wrappers in `finllm.py` are designed to support **LoRA (Low-Rank Adaptation)** fine-tuning out-of-the-box via the `peft` library. This allows developers to load a base model and merge LoRA weights dynamically, which is crucial for efficient experimentation and deployment of specialized financial models.
*   **Dual Interface for Demonstration**: Providing both a **Command-Line Interface (`cli_demo.py`)** and a **Web Interface (`web_demo.py`)** using Streamlit enhances the project's **accessibility and usability**. This dual approach caters to both developers who prefer a quick terminal check and end-users who need a more polished, graphical demonstration.

### 3.4. Summary & Recommendations

#### 3.4.1. Potential Improvements

While the project is well-structured, several areas could be improved to enhance performance, architectural robustness, and code quality.

## 1. Architectural Optimization: Model Loading
*   **Suggestion**: Implement a **Singleton Pattern** or a dedicated **Model Manager** class for the LLM.
*   **Reasoning**: Currently, the model loading logic is duplicated across the demo scripts and the evaluation wrappers, and the evaluation wrappers themselves contain repetitive model loading code. A Singleton pattern would ensure the large LLM is loaded only once per process, centralizing resource management and reducing memory overhead.

## 2. Code Quality: Refactoring `evaluate.py`
*   **Suggestion**: Introduce a common `BaseEvaluator` class in `evaluate.py` to abstract common methods like `__init__`, `run_evaluation`, and prompt building logic.
*   **Reasoning**: The current `evaluate.py` file is excessively long (nearly 1000 lines) due to the high degree of code duplication across the many `*Evaluator` classes. Abstracting the common structure (loading data, iterating samples, calling `llm.generate`, calculating metrics) would significantly reduce file size and improve maintainability.

## 3. Robustness and Error Handling
*   **Suggestion**: Enhance error handling, particularly in `preprocess.py` and model loading.
*   **Reasoning**: The `preprocess.py` download function only prints an error message on failure (`print('failed to download dataset {}, {}'.format(eval_dataset, e))`) but does not raise an exception or retry. In a production environment, network failures should be handled with retries or graceful failure. Similarly, model loading should include more robust exception handling for missing files or incompatible hardware.

## 4. Performance: Text Processing
*   **Suggestion**: Replace the dependency on `nltk` for simple Chinese segmentation and punctuation removal in `utils.py` with a lighter, custom regex-based function or a more modern, dedicated Chinese NLP library like `jieba`.
*   **Reasoning**: The current implementation relies on `nltk.word_tokenize`, which may not be optimized for Chinese text and introduces a heavy dependency for simple tasks. A more streamlined approach could improve the performance of the metric calculation step.

#### 3.4.2. Secondary Development Guide

This guide outlines the best path for developers looking to explore, modify, or extend the DISC-FinLLM project.

## 1. Code Exploration and Entry Points
*   **Application Flow**: Start with `cli_demo.py` to understand how the model is loaded (`init_model`) and how the chat loop is managed. This is the simplest entry point for testing model responses.
*   **Evaluation Flow**: The core logic is orchestrated by `autoeval.py`. Examine this file to see how models and evaluators are instantiated using the Factory Pattern.
*   **Model Abstraction**: Study `eval/evaluator/finllm.py`. This file is crucial for understanding how different LLMs are wrapped and how LoRA weights are integrated.

## 2. Extending Model Support
To integrate a new LLM (e.g., Llama-3):
1.  Create a new class in `finllm.py` (e.g., `DISCVFINLLMLlama3`) inheriting from `DISCFINLLMBase`.
2.  Implement the `__init__` method to handle the specific model and tokenizer loading for Llama-3, including any necessary `trust_remote_code` or LoRA integration.
3.  Implement the `generate(prompt: str)` method, ensuring it correctly formats the prompt and calls the model's generation function to return a clean string response.
4.  Add the new class to the `model_lists` dictionary in `autoeval.py`.

## 3. Adding a New Evaluation Task
To add a new financial NLP task:
1.  Create a new class in `evaluate.py` (e.g., `FinNewTaskEvaluator`) following the structure of existing evaluators.
2.  Define the `zero_shot_prompts` and `few_shot_prompts` templates specific to the new task.
3.  Implement the `evaluate(golds, preds)` static method to calculate the correct metric (e.g., F1, accuracy, exact match) for the task, leveraging helper functions in `utils.py`.
4.  Add the new evaluator class to the `Eval_datasets` dictionary in `autoeval.py`.

## 4. Customizing Data and Metrics
*   **Data**: The `preprocess.py` script is the place to modify how raw data is converted into the standardized `input`/`gold_answer` format.
*   **Metrics**: The `utils.py` file contains the core logic for text cleaning (`_mixed_segmentation`) and metric calculation (`_compute_f1_score`). Modifications here will affect all generative evaluation tasks.

