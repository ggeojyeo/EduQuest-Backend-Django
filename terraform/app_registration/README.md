# EduQuest App Registration Terraform (No Subscription Required)

This Terraform module creates Entra ID (Azure AD) app registrations for:
- Backend API
- Frontend SPA

It uses only the `azuread` provider, so it works in a tenant/account with **no Azure subscription**.
It mirrors your portal setup:
- Backend app: **eduquest-ntu-backend**
- Frontend app: **eduquest-ntu-frontend**
- Sign-in audience for both apps: **AzureADMultipleOrgs** (multi-tenant)
- Backend exposed scope: **user_impersonation**
- Backend API identifier URI: **api://<backend-client-id>**
- Frontend API permissions: backend scope + Graph `User.Read`, `User.ReadBasic.All`
- Backend pre-authorized clients: frontend app
- Backend client secrets: **django** and **postman**
- Backend web redirect URI: **https://oauth.pstmn.io/v1/browser-callback**
- Backend API permissions: Graph `User.Read`, `User.ReadBasic.All`
- Frontend tenant-wide admin consent is automated in Terraform (requires directory admin role)

## 1. Login to tenant account

```bash
az login --tenant <TENANT_ID> --use-device-code --allow-no-subscriptions
```

## 2. Go to folder

```bash
cd terraform\app_registration
```

Defaults are already embedded in `variables.tf` to mirror your report figures.
You only need `terraform.tfvars` if you want to override those defaults.
If `terraform.tfvars` exists, remove `backend_identifier_uri` from it so backend API URI is always `api://<backend-client-id>`.

## 3. Apply

```bash
terraform init
terraform apply
```

If you want Terraform to fail fast in the wrong tenant, set `expected_tenant_id` in `terraform.tfvars` before applying.

## 4. Verify app wiring

After `terraform apply`, verify that the frontend permission wiring points at the current backend app and current backend scope:

```powershell
.\verify-app-registration.ps1
```

This checks:
- current tenant ID
- backend app ID
- frontend app ID
- frontend `requiredResourceAccess` -> current backend app ID
- frontend delegated scope -> current backend scope ID
- backend pre-authorization -> current frontend app ID + current backend scope ID

## 5. Use outputs in infra Terraform

Copy these outputs into your main infrastructure variables:
- `backend_client_id` -> `azure_ad_client_id`
- `backend_django_client_secret` -> `azure_ad_client_secret`
- `frontend_client_id` -> `frontend_azure_client_id`
- `login_request_scope` -> `login_request_scope`

Get outputs:

```bash
terraform output
terraform output -raw backend_client_secret
```

