# ============================================
# EDUQUEST - ALL IN ONE TERRAFORM (TEST ENV)
# ============================================
# Creates: Eduquest resource group with:
# - ASP-RGEduquest-acaa (App Service plan)
# - eduquest-backend (App Service)
# - eduquest-db (PostgreSQL)
# - eduquest-frontend (App Service)
# - eduquest-microservice (App Service)
# - eduqueststorage (Storage account)
# - Azure OpenAI (with GPT deployment)
#
# NOTE: Azure AD App Registrations must be created manually
#       in your organization's Azure AD tenant.
#
# Usage:
#   terraform init
#   terraform apply

terraform {
  required_version = ">= 1.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 3.37.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.0"
    }
  }
}

provider "azurerm" {
  features {
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
    cognitive_account {
      purge_soft_delete_on_destroy = true
    }
  }

  # Skip automatic resource provider registration (requires higher permissions)
  skip_provider_registration = true
}

data "terraform_remote_state" "app_registration" {
  count   = var.use_app_registration_outputs ? 1 : 0
  backend = "local"
  config = {
    path = "${path.module}/../app_registration/terraform.tfstate"
  }
}

# ============================================
# LOCALS - Auto-generate names from base_name
# ============================================
locals {
  rg_name           = "${title(var.base_name)}-ntu"
  app_plan_name     = "ASP-RG${title(var.base_name)}-acaa"
  backend_name      = "${var.base_name}-ntu-backend"
  frontend_name     = "${var.base_name}-ntu-frontend"
  microservice_name = "${var.base_name}-ntu-microservice"
  server_name       = "${var.base_name}-ntu-db"
  storage_name      = "${var.base_name}ntustorage"
  appreg_outputs    = var.use_app_registration_outputs ? data.terraform_remote_state.app_registration[0].outputs : {}

  resolved_azure_ad_client_id = try(coalesce(
    try(var.azure_ad_client_id, null),
    try(local.appreg_outputs.backend_client_id, null)
  ), "")
  resolved_azure_ad_client_secret = try(coalesce(
    try(var.azure_ad_client_secret, null),
    try(local.appreg_outputs.backend_django_client_secret, null),
    try(local.appreg_outputs.backend_client_secret, null)
  ), "")
  resolved_frontend_azure_client_id = try(coalesce(
    try(var.frontend_azure_client_id, null),
    try(local.appreg_outputs.frontend_client_id, null)
  ), "")
  resolved_login_request_scope = try(coalesce(
    try(var.login_request_scope, null),
    try(local.appreg_outputs.login_request_scope, null)
  ), "")

  # Database configuration - use existing or create new
  db_host     = var.use_existing_database ? var.existing_database_host : azurerm_postgresql_flexible_server.main[0].fqdn
  db_name     = var.use_existing_database ? var.existing_database_name : "eduquest"
  db_user     = var.use_existing_database ? var.existing_database_user : "eduadmin"
  db_password = var.use_existing_database ? var.existing_database_password : random_password.db_password.result
  db_port     = var.use_existing_database ? var.existing_database_port : "5432"
}

# ============================================
# RANDOM PASSWORD FOR DATABASE & SECRET KEY
# ============================================
resource "random_password" "db_password" {
  length           = 24
  special          = true
  override_special = "!#$%&*"
}

resource "random_password" "secret_key" {
  length  = 50
  special = true
}

resource "random_string" "unique_suffix" {
  length  = 6
  lower   = true
  upper   = false
  number  = true
  special = false
}

# ============================================
# 1. RESOURCE GROUP (Use existing or create new)
# ============================================
data "azurerm_resource_group" "main" {
  count = var.use_existing_resources ? 1 : 0
  name  = var.existing_resource_group_name
}

resource "azurerm_resource_group" "main" {
  count    = var.use_existing_resources ? 0 : 1
  name     = local.rg_name
  location = var.location
}

locals {
  resource_group_name     = var.use_existing_resources ? data.azurerm_resource_group.main[0].name : azurerm_resource_group.main[0].name
  resource_group_location = var.use_existing_resources ? data.azurerm_resource_group.main[0].location : azurerm_resource_group.main[0].location
}

# ============================================
# 2. AZURE OPENAI
# ============================================
resource "azurerm_cognitive_account" "openai" {
  count                 = var.deploy_openai ? 1 : 0
  name                  = var.openai_resource_name
  resource_group_name   = local.resource_group_name
  location              = var.openai_location
  kind                  = "OpenAI"
  sku_name              = "S0"
  custom_subdomain_name = var.openai_custom_subdomain_name
}

resource "azurerm_cognitive_deployment" "gpt" {
  count                = var.deploy_openai ? 1 : 0
  name                 = var.openai_deployment_name
  cognitive_account_id = azurerm_cognitive_account.openai[0].id

  model {
    format  = "OpenAI"
    name    = var.openai_model_name
    version = var.openai_model_version
  }

  scale {
    type     = "Standard"
    capacity = var.openai_capacity
  }
}

# ============================================
# 5. APP SERVICE PLAN (Use existing or create new)
# ============================================
data "azurerm_service_plan" "main" {
  count               = var.use_existing_resources ? 1 : 0
  name                = var.existing_app_service_plan_name
  resource_group_name = var.existing_app_service_plan_resource_group_name != "" ? var.existing_app_service_plan_resource_group_name : local.resource_group_name
}

resource "azurerm_service_plan" "main" {
  count               = var.use_existing_resources ? 0 : 1
  name                = local.app_plan_name
  resource_group_name = local.resource_group_name
  location            = local.resource_group_location
  os_type             = "Linux"
  sku_name            = "F1"
}

locals {
  service_plan_id       = var.use_existing_resources ? data.azurerm_service_plan.main[0].id : azurerm_service_plan.main[0].id
  service_plan_location = var.use_existing_resources ? data.azurerm_service_plan.main[0].location : azurerm_service_plan.main[0].location
}

# ============================================
# 6. STORAGE ACCOUNT
# ============================================
resource "azurerm_storage_account" "main" {
  count                    = var.deploy_storage ? 1 : 0
  name                     = local.storage_name
  resource_group_name      = local.resource_group_name
  location                 = local.resource_group_location
  account_tier             = "Standard"
  account_replication_type = "RAGRS"

  blob_properties {
    cors_rule {
      allowed_origins    = ["*"]
      allowed_methods    = ["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"]
      allowed_headers    = ["*"]
      exposed_headers    = ["*"]
      max_age_in_seconds = 3600
    }
  }
}

resource "azurerm_storage_container" "media" {
  count                 = var.deploy_storage ? 1 : 0
  name                  = "eduquest-container"
  storage_account_name  = azurerm_storage_account.main[0].name
  container_access_type = "blob"
}

# ============================================
# 4. POSTGRESQL DATABASE (Create new or use existing)
# ============================================
resource "azurerm_postgresql_flexible_server" "main" {
  count                  = var.use_existing_database ? 0 : 1
  name                   = local.server_name
  resource_group_name    = local.resource_group_name
  location               = local.resource_group_location
  version                = "15"
  administrator_login    = "eduadmin"
  administrator_password = random_password.db_password.result
  storage_mb             = 32768
  sku_name               = "B_Standard_B1ms"
  zone                   = "3"
}

resource "azurerm_postgresql_flexible_server_database" "main" {
  count     = var.use_existing_database ? 0 : 1
  name      = "eduquest"
  server_id = azurerm_postgresql_flexible_server.main[0].id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "azure" {
  count            = var.use_existing_database ? 0 : 1
  name             = "AllowAzureServices"
  server_id        = azurerm_postgresql_flexible_server.main[0].id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "255.255.255.255"
}

# ============================================
# 5. BACKEND APP SERVICE (Docker Compose)
# ============================================
locals {
  backend_compose = <<-EOF
services:
  app:
    image: zchua040/eduquest-backend-django:latest
    ports:
      - "8000:8000"
    environment:
      - REDIS_HOST=redis
      - SECRET_KEY=$${SECRET_KEY}
      - ALLOWED_HOSTS=$${ALLOWED_HOSTS}
      - DB_NAME=$${DB_NAME}
      - DB_USER=$${DB_USER}
      - DB_PASSWORD=$${DB_PASSWORD}
      - DB_HOST=$${DB_HOST}
      - DB_PORT=$${DB_PORT}
      - AZURE_AD_CLIENT_ID=$${AZURE_AD_CLIENT_ID}
      - AZURE_AD_CLIENT_SECRET=$${AZURE_AD_CLIENT_SECRET}
      - AZURE_ACCOUNT_NAME=$${AZURE_ACCOUNT_NAME}
      - AZURE_ACCOUNT_KEY=$${AZURE_ACCOUNT_KEY}
      - AZURE_CONTAINER=$${AZURE_CONTAINER}
      - AZURE_STORAGE_ACCOUNT_CONNECTION_STRING=$${AZURE_STORAGE_ACCOUNT_CONNECTION_STRING}
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/0
    dns:
      - 8.8.8.8
      - 8.8.4.4

  celery:
    image: zchua040/eduquest-backend-django:latest
    command: celery -A core worker --loglevel=info
    environment:
      - REDIS_HOST=redis
      - SECRET_KEY=$${SECRET_KEY}
      - ALLOWED_HOSTS=$${ALLOWED_HOSTS}
      - DB_NAME=$${DB_NAME}
      - DB_USER=$${DB_USER}
      - DB_PASSWORD=$${DB_PASSWORD}
      - DB_HOST=$${DB_HOST}
      - DB_PORT=$${DB_PORT}
      - AZURE_AD_CLIENT_ID=$${AZURE_AD_CLIENT_ID}
      - AZURE_AD_CLIENT_SECRET=$${AZURE_AD_CLIENT_SECRET}
      - AZURE_ACCOUNT_NAME=$${AZURE_ACCOUNT_NAME}
      - AZURE_ACCOUNT_KEY=$${AZURE_ACCOUNT_KEY}
      - AZURE_CONTAINER=$${AZURE_CONTAINER}
      - AZURE_STORAGE_ACCOUNT_CONNECTION_STRING=$${AZURE_STORAGE_ACCOUNT_CONNECTION_STRING}
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/0
    dns:
      - 8.8.8.8
      - 8.8.4.4

  celery-beat:
    image: zchua040/eduquest-backend-django:latest
    command: celery -A core beat --loglevel=info
    environment:
      - REDIS_HOST=redis
      - SECRET_KEY=$${SECRET_KEY}
      - ALLOWED_HOSTS=$${ALLOWED_HOSTS}
      - DB_NAME=$${DB_NAME}
      - DB_USER=$${DB_USER}
      - DB_PASSWORD=$${DB_PASSWORD}
      - DB_HOST=$${DB_HOST}
      - DB_PORT=$${DB_PORT}
      - AZURE_AD_CLIENT_ID=$${AZURE_AD_CLIENT_ID}
      - AZURE_AD_CLIENT_SECRET=$${AZURE_AD_CLIENT_SECRET}
      - AZURE_ACCOUNT_NAME=$${AZURE_ACCOUNT_NAME}
      - AZURE_ACCOUNT_KEY=$${AZURE_ACCOUNT_KEY}
      - AZURE_CONTAINER=$${AZURE_CONTAINER}
      - AZURE_STORAGE_ACCOUNT_CONNECTION_STRING=$${AZURE_STORAGE_ACCOUNT_CONNECTION_STRING}
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/0
    dns:
      - 8.8.8.8
      - 8.8.4.4

  redis:
    image: "redis:alpine"
    ports:
      - "6379:6379"
EOF
}

resource "azurerm_linux_web_app" "backend" {
  count               = var.deploy_backend ? 1 : 0
  name                = local.backend_name
  resource_group_name = local.resource_group_name
  location            = local.service_plan_location
  service_plan_id     = local.service_plan_id
  https_only          = true

  site_config {
    always_on = false
    application_stack {
      docker_image_name   = "zchua040/eduquest-backend-django:latest"
      docker_registry_url = "https://index.docker.io"
    }
  }

  app_settings = merge(
    {
      "DOCKER_ENABLE_CI"                    = "true"
      "WEBSITES_ENABLE_APP_SERVICE_STORAGE" = "false"
      "DB_HOST"                             = local.db_host
      "DB_NAME"                             = local.db_name
      "DB_USER"                             = local.db_user
      "DB_PASSWORD"                         = local.db_password
      "DB_PORT"                             = local.db_port
      "SECRET_KEY"                          = random_password.secret_key.result
      "ALLOWED_HOSTS"                       = "localhost,127.0.0.1,${local.backend_name}.azurewebsites.net"
      "AZURE_AD_CLIENT_ID"                  = local.resolved_azure_ad_client_id
      "AZURE_AD_CLIENT_SECRET"              = local.resolved_azure_ad_client_secret
    },
    var.deploy_storage ? {
      "AZURE_ACCOUNT_NAME"                      = azurerm_storage_account.main[0].name
      "AZURE_ACCOUNT_KEY"                       = azurerm_storage_account.main[0].primary_access_key
      "AZURE_CONTAINER"                         = azurerm_storage_container.media[0].name
      "AZURE_STORAGE_ACCOUNT_CONNECTION_STRING" = azurerm_storage_account.main[0].primary_connection_string
    } : {}
  )

  lifecycle {
    ignore_changes = [site_config[0].application_stack]
  }
}

resource "local_file" "backend_compose" {
  content  = local.backend_compose
  filename = "${path.module}/backend-compose.yml"
}

resource "null_resource" "backend_docker_compose" {
  count      = var.deploy_backend ? 1 : 0
  depends_on = [azurerm_linux_web_app.backend, local_file.backend_compose]

  provisioner "local-exec" {
    command = "az webapp config container set --name ${local.backend_name} --resource-group ${local.resource_group_name} --docker-registry-server-url https://index.docker.io --multicontainer-config-type compose --multicontainer-config-file ${path.module}/backend-compose.yml"
  }

  triggers = {
    always_run = timestamp()
  }
}

# ============================================
# 6. MICROSERVICE APP SERVICE (Docker Compose)
# ============================================
locals {
  microservice_compose = <<-EOF
services:
  microservice:
    image: zchua040/eduquest-microservice-flask:latest
    ports:
      - "80:5000"
    environment:
      WEBSITES_PORT: $${WEBSITES_PORT}
      AZURE_STORAGE_CONNECTION_STRING: $${AZURE_STORAGE_CONNECTION_STRING}
      AZURE_STORAGE_CONTAINER_NAME: $${AZURE_STORAGE_CONTAINER_NAME}
      AZURE_OPENAI_API_KEY: $${AZURE_OPENAI_API_KEY}
      AZURE_OPENAI_ENDPOINT: $${AZURE_OPENAI_ENDPOINT}
      AZURE_OPENAI_DEPLOYMENT_NAME: $${AZURE_OPENAI_DEPLOYMENT_NAME}
      AZURE_OPENAI_API_VERSION: $${AZURE_OPENAI_API_VERSION}
      AZURE_OPENAI_TEMPERATURE: $${AZURE_OPENAI_TEMPERATURE}

EOF
}

resource "azurerm_linux_web_app" "microservice" {
  count               = var.deploy_microservice ? 1 : 0
  name                = local.microservice_name
  resource_group_name = local.resource_group_name
  location            = local.service_plan_location
  service_plan_id     = local.service_plan_id
  https_only          = true

  site_config {
    always_on = false
    application_stack {
      docker_image_name   = "zchua040/eduquest-microservice-flask:latest"
      docker_registry_url = "https://index.docker.io"
    }
  }

  app_settings = merge(
    {
      "DOCKER_ENABLE_CI"                    = "true"
      "WEBSITES_ENABLE_APP_SERVICE_STORAGE" = "false"
      "AZURE_OPENAI_API_VERSION"            = "2024-06-01"
      "AZURE_OPENAI_TEMPERATURE"            = "0.3"
    },
    var.deploy_storage ? {
      "AZURE_STORAGE_CONNECTION_STRING" = azurerm_storage_account.main[0].primary_connection_string
      "AZURE_STORAGE_CONTAINER_NAME"    = azurerm_storage_container.media[0].name
    } : {},
    var.deploy_openai ? {
      "AZURE_OPENAI_API_KEY"         = azurerm_cognitive_account.openai[0].primary_access_key
      "AZURE_OPENAI_ENDPOINT"        = azurerm_cognitive_account.openai[0].endpoint
      "AZURE_OPENAI_DEPLOYMENT_NAME" = azurerm_cognitive_deployment.gpt[0].name
    } : {}
  )

  lifecycle {
    ignore_changes = [site_config[0].application_stack]
  }
}

resource "local_file" "microservice_compose" {
  content  = local.microservice_compose
  filename = "${path.module}/microservice-compose.yml"
}

resource "null_resource" "microservice_docker_compose" {
  count      = var.deploy_microservice ? 1 : 0
  depends_on = [azurerm_linux_web_app.microservice, local_file.microservice_compose]

  provisioner "local-exec" {
    command = "az webapp config container set --name ${local.microservice_name} --resource-group ${local.resource_group_name} --docker-registry-server-url https://index.docker.io --multicontainer-config-type compose --multicontainer-config-file ${path.module}/microservice-compose.yml"
  }

  triggers = {
    always_run = timestamp()
  }
}

# ============================================
# 7. FRONTEND APP SERVICE (Docker Compose)
# ============================================
locals {
  frontend_compose = <<-EOF
services:
  frontend:
    image: zchua040/eduquest-frontend-reactjs:latest
    ports:
      - "80:80"
    environment:
      NEXT_PUBLIC_SITE_URL: $${NEXT_PUBLIC_SITE_URL}
      NEXT_PUBLIC_AZURE_CLIENT_ID: $${NEXT_PUBLIC_AZURE_CLIENT_ID}
      NEXT_PUBLIC_AZURE_REDIRECT_URI: $${NEXT_PUBLIC_AZURE_REDIRECT_URI}
      NEXT_PUBLIC_BACKEND_URL: $${NEXT_PUBLIC_BACKEND_URL}
      NEXT_PUBLIC_MICROSERVICE_URL: $${NEXT_PUBLIC_MICROSERVICE_URL}
      NEXT_PUBLIC_LOGIN_REQUEST_SCOPE: $${NEXT_PUBLIC_LOGIN_REQUEST_SCOPE}
EOF
}

resource "azurerm_linux_web_app" "frontend" {
  count               = var.deploy_frontend ? 1 : 0
  name                = local.frontend_name
  resource_group_name = local.resource_group_name
  location            = local.service_plan_location
  service_plan_id     = local.service_plan_id
  https_only          = true

  site_config {
    always_on = false
    application_stack {
      docker_image_name   = "zchua040/eduquest-frontend-reactjs:latest"
      docker_registry_url = "https://index.docker.io"
    }
  }

  app_settings = {
    "DOCKER_ENABLE_CI"                    = "true"
    "WEBSITES_ENABLE_APP_SERVICE_STORAGE" = "false"
    "NEXT_PUBLIC_BACKEND_URL"             = "https://${local.backend_name}.azurewebsites.net"
    "NEXT_PUBLIC_MICROSERVICE_URL"        = "https://${local.microservice_name}.azurewebsites.net"
    "NEXT_PUBLIC_SITE_URL"                = "https://${local.frontend_name}.azurewebsites.net"
    "NEXT_PUBLIC_AZURE_CLIENT_ID"         = local.resolved_frontend_azure_client_id
    "NEXT_PUBLIC_AZURE_REDIRECT_URI"      = "https://${local.frontend_name}.azurewebsites.net"
    "NEXT_PUBLIC_LOGIN_REQUEST_SCOPE"     = local.resolved_login_request_scope
  }

  lifecycle {
    ignore_changes = [site_config[0].application_stack]
  }
}

resource "local_file" "frontend_compose" {
  content  = local.frontend_compose
  filename = "${path.module}/frontend-compose.yml"
}

resource "null_resource" "frontend_docker_compose" {
  count      = var.deploy_frontend ? 1 : 0
  depends_on = [azurerm_linux_web_app.frontend, local_file.frontend_compose]

  provisioner "local-exec" {
    command = "az webapp config container set --name ${local.frontend_name} --resource-group ${local.resource_group_name} --docker-registry-server-url https://index.docker.io --multicontainer-config-type compose --multicontainer-config-file ${path.module}/frontend-compose.yml"
  }

  triggers = {
    always_run = timestamp()
  }
}

# ============================================
# OUTPUTS
# ============================================
output "resource_group" {
  value = local.resource_group_name
}

output "backend_url" {
  value = var.deploy_backend ? "https://${azurerm_linux_web_app.backend[0].default_hostname}" : null
}

output "microservice_url" {
  value = var.deploy_microservice ? "https://${azurerm_linux_web_app.microservice[0].default_hostname}" : null
}

output "frontend_url" {
  value = var.deploy_frontend ? "https://${azurerm_linux_web_app.frontend[0].default_hostname}" : null
}

output "db_password" {
  value     = random_password.db_password.result
  sensitive = true
}

output "storage_connection_string" {
  value     = var.deploy_storage ? azurerm_storage_account.main[0].primary_connection_string : null
  sensitive = true
}

# Azure OpenAI outputs (auto-created)
output "openai_endpoint" {
  description = "Azure OpenAI endpoint URL"
  value       = var.deploy_openai ? azurerm_cognitive_account.openai[0].endpoint : null
}

output "openai_api_key" {
  description = "Azure OpenAI API key"
  value       = var.deploy_openai ? azurerm_cognitive_account.openai[0].primary_access_key : null
  sensitive   = true
}

output "openai_deployment_name" {
  description = "Azure OpenAI deployment name"
  value       = var.deploy_openai ? azurerm_cognitive_deployment.gpt[0].name : null
}
