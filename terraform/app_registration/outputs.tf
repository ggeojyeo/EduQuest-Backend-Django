output "tenant_id" {
  description = "Tenant ID where app registrations were created."
  value       = data.azuread_client_config.current.tenant_id
}

output "backend_client_id" {
  description = "Backend app registration client ID."
  value       = azuread_application.backend.client_id
}

output "backend_scope_id" {
  description = "Backend exposed scope ID used by the frontend delegated permission."
  value       = local.backend_scope_id
}

output "backend_identifier_uri" {
  description = "Backend API identifier URI."
  value       = "api://${azuread_application.backend.client_id}"
}

output "backend_client_secret" {
  description = "Backend app registration client secret for Django."
  value       = azuread_application_password.backend.value
  sensitive   = true
}

output "backend_django_client_secret" {
  description = "Backend app registration Django client secret."
  value       = azuread_application_password.backend.value
  sensitive   = true
}

output "backend_postman_client_secret" {
  description = "Backend app registration Postman client secret."
  value       = azuread_application_password.backend_postman.value
  sensitive   = true
}

output "frontend_client_id" {
  description = "Frontend app registration client ID."
  value       = azuread_application.frontend.client_id
}

output "login_request_scope" {
  description = "Scope value for frontend login requests."
  value       = "api://${azuread_application.backend.client_id}/${var.backend_scope_value}"
}

output "frontend_expected_backend_resource_app_id" {
  description = "Backend app ID that the frontend should reference in required_resource_access."
  value       = azuread_application.backend.client_id
}

