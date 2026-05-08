variable "project_name" {
  description = "Base project name used in app display names."
  type        = string
  default     = "eduquest"
}

variable "environment" {
  description = "Environment label appended to app display names."
  type        = string
  default     = "ntu"
}

variable "expected_tenant_id" {
  description = "Expected Microsoft Entra tenant ID. When set, Terraform fails if you are logged into a different tenant."
  type        = string
  default     = null
  nullable    = true
}

variable "backend_display_name" {
  description = "Backend app registration display name."
  type        = string
  default     = "eduquest-ntu-backend"
}

variable "frontend_display_name" {
  description = "Frontend app registration display name."
  type        = string
  default     = "eduquest-ntu-frontend"
}

variable "backend_identifier_uri" {
  description = "Deprecated: backend identifier URI is managed as api://<backend-client-id>."
  type        = string
  default     = null
  nullable    = true
}

variable "backend_redirect_uris" {
  description = "Redirect URIs for backend app registration."
  type        = list(string)
  default = [
    "https://oauth.pstmn.io/v1/browser-callback"
  ]
}

variable "frontend_redirect_uris" {
  description = "Redirect URIs for frontend SPA app registration."
  type        = list(string)
  default = [
    "https://eduquest-frontend.azurewebsites.net/auth/sign-in",
    "https://eduquest-frontend.azurewebsites.net",
    "http://localhost:3000/"
  ]
}

variable "frontend_logout_url" {
  description = "Frontend logout URL."
  type        = string
  default     = null
  nullable    = true
}

variable "access_token_lifetime_hours" {
  description = "Backend secret lifetime in hours."
  type        = number
  default     = 8760
}

variable "backend_scope_value" {
  description = "OAuth scope value exposed by backend API."
  type        = string
  default     = "user_impersonation"
}

