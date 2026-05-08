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

variable "use_existing_resources" {
  description = "Whether to use existing resource group and app service plan"
  type        = bool
  default     = true
}
