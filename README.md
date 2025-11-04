# KPI Factory

This project is a complete code scaffold for a "KPI Factory" – a system where real-time data streams can be used to generate Key Performance Indicators (KPIs), which are then tokenized as ERC-20 tokens on an EVM-compatible blockchain. The system is designed to be self-evolving, with an AI/LLM-driven layer for appraising prompts and justifying the creation and valuation of KPIs.

## Project Architecture

The project is divided into three main components:

1.  **Smart Contracts (`/contracts`)**: The on-chain foundation of the system, written in Solidity.
2.  **Backend Service (`/backend`)**: A Python FastAPI application that serves as the central hub for KPI management, data streaming, and prompt appraisal.
3.  **Scripts (`/scripts`)**: Utility scripts for interacting with the system, such as the off-chain oracle feeder.

### Smart Contracts

-   `KPIRegistry.sol`: A factory contract that deploys and keeps track of all KPI tokens and their associated oracles.
-   `KPIOracle.sol`: A simple, signable oracle contract that stores the latest value for a given KPI.
-   `KPIToken.sol`: An ERC-20 token template for KPIs. It includes a `sync()` function that mints new tokens based on positive changes in its oracle's value.

### Backend Service

-   **REST API**: Provides endpoints for creating new KPIs, listing existing ones, and appraising prompts against the live KPI set.
-   **WebSocket**: Streams real-time value updates for each KPI to subscribed clients.
-   **LLM Integration (Placeholder)**: Includes placeholder logic for where an LLM would be used to score prompts and propose new KPIs.

## Getting Started

### Prerequisites

-   Python 3.8+
-   An Ethereum development environment for compiling and deploying Solidity contracts (e.g., Hardhat or Foundry).
-   `pip` for installing Python packages.

### Installation

1.  **Install Smart Contract Dependencies**:
    This project uses OpenZeppelin contracts. You will need to set up a Hardhat or Foundry project and install the necessary dependencies. For example, with Hardhat:
    ```bash
    # (Inside a new hardhat project)
    npm install @openzeppelin/contracts
    ```

2.  **Install Backend Dependencies**:
    ```bash
    pip install -r backend/requirements.txt
    ```

3.  **Install Script Dependencies**:
    ```bash
    pip install -r scripts/requirements.txt
    ```

### Running the System

1.  **Compile and Deploy the Smart Contracts**:
    -   Using your chosen development framework (e.g., Hardhat), compile the contracts in the `contracts/` directory.
    -   Deploy the `KPIRegistry.sol` contract to your target blockchain (e.g., a local testnet like Hardhat Network). This step would require a deployment script, which is not included in this scaffold but would be necessary for a full deployment.

2.  **Run the Backend Service**:
    Navigate to the root directory of the project and run:
    ```bash
    uvicorn backend.main:app --reload
    ```
    The service will be available at `http://localhost:8000`.

3.  **Seed the KPI Factory**:
    In a new terminal, run the oracle feeder script to populate the backend with the 30 sample KPIs:
    ```bash
    python scripts/oracle_feeder.py
    ```
    This will start the real-time data simulation for all seeded KPIs.

4.  **Connect to a Live Feed**:
    You can connect to the WebSocket endpoint for any of the seeded KPIs to see a live stream of its value updates. For example, using a tool like `websocat`:
    ```bash
    # (Ticker will be printed by the feeder script, e.g., ENTR01)
    websocat ws://localhost:8000/ws/kpi/ENTR01
    ```

## API Endpoints

-   `POST /kpis`: Create a new KPI.
    -   **Body**: `{ "name": "My KPI", "description": "...", "formula": "..." }`
-   `GET /kpis`: List all active KPIs.
-   `POST /appraise`: Appraise a prompt.
    -   **Body**: `{ "text": "This is a sample prompt." }`
-   `ws://localhost:8000/ws/kpi/{ticker}`: WebSocket connection for live KPI updates.
