# Email Agent System

This system processes emails from a RabbitMQ queue, identifies private jet charter requests using OpenAI's LLM, and responds with appropriate actions.

## Features

- RabbitMQ integration for email queue processing
- OpenAI GPT-4 integration for email analysis
- BCC functionality for team notifications

## Setup

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and fill in your credentials:
   ```bash
   cp .env.example .env
   ```
5. Configure the following environment variables in `.env`:
   - OpenAI API key
   - RabbitMQ credentials

## Running RabbitMQ with Docker

The project includes a Docker Compose file to run RabbitMQ locally:

1. Start RabbitMQ:
   ```bash
   docker-compose up -d
   ```

2. Access the RabbitMQ Management UI:
   - Open your browser and navigate to http://localhost:15672
   - Login with username: `guest` and password: `guest`

3. Stop RabbitMQ when done:
   ```bash
   docker-compose down
   ```

## Usage

1. Ensure RabbitMQ is running (either via Docker or installed locally)
2. Run the application:
   ```bash
   python main.py
   ```

## Project Structure

- `main.py`: Application entry point
- `src/`
  - `email_processor.py`: Main orchestration logic
  - `rabbitmq_client.py`: RabbitMQ integration
  - `llm_analyzer.py`: OpenAI integration
- `docker-compose.yml`: Docker configuration for RabbitMQ

## Adding External API Integration

To add your external API integration for gathering email addresses:

1. Create a new method in the `EmailProcessor` class
2. Replace the TODO comment in `process_email` method with your API call
3. Update the email addresses list with the API response

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request 
