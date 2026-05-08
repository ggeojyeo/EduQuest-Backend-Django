data "azuread_client_config" "current" {}
data "azuread_service_principal" "microsoft_graph" {
  client_id = "00000003-0000-0000-c000-000000000000"
}

locals {
  # Keep scope ID stable to match the expected portal/API-permissions wiring.
  backend_scope_id = "157b883c-8a26-4bdc-dea9-a73c24cda3dc"
  tenant_id        = data.azuread_client_config.current.tenant_id

  frontend_redirect_uris = distinct([
    for uri in var.frontend_redirect_uris :
    can(regex("^https?://[^/]+$", uri)) ? "${uri}/" : uri
  ])
}

resource "azuread_application" "backend" {
  display_name     = var.backend_display_name
  sign_in_audience = "AzureADMultipleOrgs"
  owners           = [data.azuread_client_config.current.object_id]

  web {
    redirect_uris = var.backend_redirect_uris
    implicit_grant {
      access_token_issuance_enabled = false
      id_token_issuance_enabled     = false
    }
  }

  api {
    mapped_claims_enabled          = false
    requested_access_token_version = 2

    oauth2_permission_scope {
      admin_consent_description  = "Allows the app to access the API as user"
      admin_consent_display_name = "Access API as user"
      enabled                    = true
      id                         = local.backend_scope_id
      type                       = "User"
      user_consent_description   = "Access API as you"
      user_consent_display_name  = "Access API as user"
      value                      = var.backend_scope_value
    }
  }

  required_resource_access {
    resource_app_id = "00000003-0000-0000-c000-000000000000"

    resource_access {
      id   = "e1fe6dd8-ba31-4d61-89e7-88639da4683d"
      type = "Scope"
    }
  }

  lifecycle {
    precondition {
      condition     = var.expected_tenant_id == null || var.expected_tenant_id == local.tenant_id
      error_message = "Connected tenant does not match var.expected_tenant_id. Run `az login --tenant <TENANT_ID> --use-device-code --allow-no-subscriptions` with the intended tenant before applying."
    }
  }
}

resource "azuread_application_identifier_uri" "backend" {
  application_id = azuread_application.backend.id
  identifier_uri = "api://${azuread_application.backend.client_id}"
}

resource "azuread_service_principal" "backend" {
  client_id = azuread_application.backend.client_id
}

resource "azuread_application_password" "backend" {
  application_id = azuread_application.backend.id
  display_name   = "django"
  end_date       = timeadd(timestamp(), "${var.access_token_lifetime_hours}h")
}

resource "azuread_application_password" "backend_postman" {
  application_id = azuread_application.backend.id
  display_name   = "postman"
  end_date       = timeadd(timestamp(), "${var.access_token_lifetime_hours}h")
}

resource "azuread_application" "frontend" {
  display_name     = var.frontend_display_name
  sign_in_audience = "AzureADMultipleOrgs"

  single_page_application {
    redirect_uris = local.frontend_redirect_uris
  }

  web {
    logout_url = var.frontend_logout_url
    implicit_grant {
      access_token_issuance_enabled = true
      id_token_issuance_enabled     = true
    }
  }

  required_resource_access {
    resource_app_id = azuread_application.backend.client_id

    resource_access {
      id   = local.backend_scope_id
      type = "Scope"
    }
  }

  required_resource_access {
    resource_app_id = "00000003-0000-0000-c000-000000000000"

    resource_access {
      id   = "e1fe6dd8-ba31-4d61-89e7-88639da4683d"
      type = "Scope"
    }
  }
}

resource "azuread_service_principal" "frontend" {
  client_id = azuread_application.frontend.client_id
}

resource "azuread_application_pre_authorized" "backend_trust_frontend" {
  application_id       = azuread_application.backend.id
  authorized_client_id = azuread_application.frontend.client_id
  permission_ids       = [local.backend_scope_id]
}

# Tenant-wide delegated consent (equivalent to "Grant admin consent for Default Directory")
resource "azuread_service_principal_delegated_permission_grant" "frontend_to_backend" {
  service_principal_object_id          = azuread_service_principal.frontend.object_id
  resource_service_principal_object_id = azuread_service_principal.backend.object_id
  claim_values                         = [var.backend_scope_value]
}

resource "azuread_service_principal_delegated_permission_grant" "frontend_to_graph" {
  service_principal_object_id          = azuread_service_principal.frontend.object_id
  resource_service_principal_object_id = data.azuread_service_principal.microsoft_graph.object_id
  claim_values                         = ["User.Read"]
}

