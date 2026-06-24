# EduQuest Backend Application (Django)

![CI](https://github.com/xeroxis-xs/EduQuest-Backend-Django/actions/workflows/main_eduquest-backend.yml/badge.svg)

## Introduction
The **EduQuest Backend Application** is the core service layer of EduQuest, a web app designed to enhance student engagement and learning performance through digital badges and gamified learning experiences. 

This backend provides essential functionalities for managing user authentication, course management, quest generation, and progress tracking, as well as integration with external tools such as Wooclap for importing quiz data.

Built using the Django REST Framework (DRF), the backend manages API requests from the frontend, handles Bearer token authentication, processes quest-related logic, and issues digital badges to students based on their achievements.

The frontend application can be found [here](https://github.com/xeroxis-xs/EduQuest-Frontend-ReactJS).

## Table of Contents
- [Architecture Overview](#architecture-overview)
- [Demo](#demo)
  - [Admin Panel](#admin-panel)
  - [API Documentation](#api-documentation)
- [Key Features](#key-features)
- [Technologies Used](#technologies-used)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Running the Application](#running-the-application)
- [Running Tests](#running-tests)

## Architecture Overview
<p align="center">
  <img src="images/backend_arch.svg" alt="Backend Architecture Diagram" width="600">
</p>

## Demo
### Admin Panel
Site: [EduQuest Admin Panel](https://eduquest-admin.azurewebsites.net/)
![img.png](images/img.png)

### API Documentation
API documentation: [Documentation](https://eduquest-admin.azurewebsites.net/docs/)
![img_1.png](images/img_1.png)


## Key Features:
- **API Management**: Provides RESTful endpoints for managing users, courses, quests, badges, and student progress.
- **User Authentication**: Secure authentication using JWT tokens from Azure Active Directory (Azure AD).
- **Course and Quest Management**: Backend logic for managing course creation, quest assignments, and tracking user participation.
- **Badge Issuance System**: Asynchronous badge validation and issuance system using Celery and Redis to ensure scalability.
- **Integration with Wooclap**: Imports quiz data and tracks student performance from Wooclap events.


## Technologies Used:
- **Django**: A Python-based web framework used for building the backend application, managing authentication, and handling server-side operations.
- **Django REST Framework (DRF)**: An extension of Django that provides a powerful toolkit for building Web APIs.
- **PostgreSQL**: A relational database used to store course, quest, user, and badge data.
- **Celery**: A distributed task queue for running asynchronous operations, such as badge validation and quest processing.
- **Redis**: Used as the message broker for Celery to handle asynchronous task execution.

## Prerequisites
- Recommended IDE: JetBrains PyCharm
- Python 3.10
- PostgreSQL

## Installation

1. **Clone the repository:**
    ```bash
    git clone https://github.com/xeroxis-xs/EduQuest-Backend-Django.git
    cd EduQuest-Backend-Django
    ```

2. **Create and activate a virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate
    ```

3. **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4. **Set up environment variables:**
    Create a `.env` file in the root directory and add the following:
    ```env
    SECRET_KEY=your_django_secret_key
    ALLOWED_HOSTS=your_allowed_hosts_ip
    DB_NAME=postgres_sql_db_name
    DB_USER=postgres_sql_db_user
    DB_PASSWORD=postgres_sql_db_password
    DB_HOST=postgres_sql_db_host
    DB_PORT=postgres_sql_db_port
    AZURE_AD_CLIENT_ID=your_registered_backend_app_client_id
    AZURE_AD_CLIENT_SECRET=your_registered_backend_app_client_secret
    AZURE_ACCOUNT_NAME=your_azure_storage_account_name
    AZURE_ACCOUNT_KEY=your_azure_storage_account_key
    AZURE_STORAGE_ACCOUNT_CONNECTION_STRING=your_azure_storage_account_connection_string
    AZURE_CONTAINER=your_azure_storage_container
    DEBUG=1_for_dev_0_for_prod
    FLASK_MICROSERVICE_URL=your_microservice_url
    ```

5. **Change Directory to the project root:**
    ```bash
    cd app
   ```

6. **Apply migrations for new database:**
    ```bash
    python manage.py migrate
    ```

7. **Create a superuser:**
    ```bash
    python manage.py createsuperuser
    ```

## Running the Application
1. **Run the development server with Redis and Celery (Recommended):**
    ```bash
   docker-compose up -d
   ```
   
1. **Run the development server without Redis and Celery:**
    ```bash
    python manage.py runserver
    ```



## Running Tests
To run all unit tests, use the following command:
```bash
python manage.py test api.tests
```