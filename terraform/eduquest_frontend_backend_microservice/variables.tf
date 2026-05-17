# ============================================
# VARIABLES
# ============================================
# Azure OpenAI is auto-created by Terraform
# Azure AD App Registrations must be created manually in your org's tenant

variable "base_name" {
  description = "Base name for all resources (e.g., eduquest)"
  type        = string
  default     = "eduquest"
}

variable "location" {
  description = "Azure region for main resources"
  type        = string
  default     = "southeastasia"
}

# ============================================
# AZURE AD (manual - from your organization's tenant)
# ============================================
variable "azure_ad_client_id" {
  description = "Azure AD Client ID for backend (from your org's App Registration)"
  type        = string
  default     = null
  nullable    = true
}

variable "azure_ad_client_secret" {
  description = "Azure AD Client Secret for backend"
  type        = string
  sensitive   = true
  default     = null
  nullable    = true
}

variable "frontend_azure_client_id" {
  description = "Azure AD Client ID for frontend (from your org's App Registration)"
  type        = string
  default     = null
  nullable    = true
}

variable "login_request_scope" {
  description = "Login request scope for frontend (e.g., api://your-app/access_as_user)"
  type        = string
  default     = null
  nullable    = true
}

variable "use_app_registration_outputs" {
  description = "Auto-read Azure AD values from ../app_registration/terraform.tfstate."
  type        = bool
  default     = true
}

# ============================================
# AZURE OPENAI CONFIG (auto-created)
# ============================================
variable "openai_location" {
  description = "Azure region for OpenAI (not all regions support OpenAI)"
  type        = string
  default     = "eastus"
}

variable "openai_resource_name" {
  description = "Name of the Azure OpenAI resource"
  type        = string
  default     = "eduquest-openaiazure"
}

variable "openai_custom_subdomain_name" {
  description = "Custom subdomain name for the Azure OpenAI endpoint"
  type        = string
  default     = "eduquest-openaiazure"
}

variable "openai_deployment_name" {
  description = "Deployment name for the OpenAI model"
  type        = string
  default     = "gpt-4o"
}

variable "openai_model_name" {
  description = "Model name to deploy"
  type        = string
  default     = "gpt-4o"
}

variable "openai_model_version" {
  description = "Model version"
  type        = string
  default     = "2024-11-20"
}

variable "openai_capacity" {
  description = "Capacity (TPM in thousands)"
  type        = number
  default     = 10
}

# ============================================
# EXISTING AZURE RESOURCES (from professor)
# ============================================
variable "existing_resource_group_name" {
  description = "Name of the existing resource group to use"
  type        = string
  default     = "05-OCA-Shared-Recourses"
}

variable "existing_app_service_plan_name" {
  description = "Name of the existing App Service Plan to use"
  type        = string
  default     = "fyp-shared-appserviceplan"
}

variable "existing_app_service_plan_resource_group_name" {
  description = "Resource group name of the existing App Service Plan (if different from main resource group)"
  type        = string
  default     = ""
}

variable "use_existing_resources" {
  description = "Whether to use existing resource group and app service plan"
  type        = bool
  default     = true
}

# ============================================
# DEPLOYMENT OPTIONS - Choose which resources to deploy
# ============================================
variable "deploy_openai" {
  description = "Deploy Azure OpenAI resource"
  type        = bool
  default     = true
}

variable "deploy_backend" {
  description = "Deploy backend web app (Django)"
  type        = bool
  default     = true
}

variable "deploy_microservice" {
  description = "Deploy microservice web app (Flask)"
  type        = bool
  default     = true
}

variable "deploy_frontend" {
  description = "Deploy frontend web app (Next.js)"
  type        = bool
  default     = true
}

variable "deploy_storage" {
  description = "Deploy storage account and container"
  type        = bool
  default     = true
}

# ============================================
# EXISTING DATABASE (from professor)
# ============================================
variable "use_existing_database" {
  description = "Whether to use an existing PostgreSQL database"
  type        = bool
  default     = false
}

variable "existing_database_host" {
  description = "Hostname of the existing PostgreSQL database"
  type        = string
  default     = ""
}

variable "existing_database_user" {
  description = "Username for the existing PostgreSQL database"
  type        = string
  default     = "postgres"
}

variable "existing_database_name" {
  description = "Database name"
  type        = string
  default     = ""
}

variable "existing_database_password" {
  description = "Password for the existing PostgreSQL database"
  type        = string
  sensitive   = true
  default     = ""
}

variable "existing_database_port" {
  description = "Port for the existing PostgreSQL database"
  type        = string
  default     = "5432"
}
