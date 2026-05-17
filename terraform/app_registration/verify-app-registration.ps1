$ErrorActionPreference = "Stop"

$outputs = terraform output -json | ConvertFrom-Json

$backendAppId = $outputs.backend_client_id.value
$frontendAppId = $outputs.frontend_client_id.value
$backendScopeId = $outputs.backend_scope_id.value
$tenantId = $outputs.tenant_id.value

$backendApp = az ad app show --id $backendAppId | ConvertFrom-Json
$frontendApp = az ad app show --id $frontendAppId | ConvertFrom-Json

$frontendBackendPermission = $frontendApp.requiredResourceAccess |
  Where-Object { $_.resourceAppId -eq $backendAppId } |
  Select-Object -First 1

if (-not $frontendBackendPermission) {
  throw "Frontend app does not reference backend appId $backendAppId in requiredResourceAccess."
}

$matchingScope = $frontendBackendPermission.resourceAccess |
  Where-Object { $_.id -eq $backendScopeId -and $_.type -eq "Scope" } |
  Select-Object -First 1

if (-not $matchingScope) {
  throw "Frontend app does not reference backend scope id $backendScopeId."
}

$backendPreAuth = $backendApp.api.preAuthorizedApplications |
  Where-Object { $_.appId -eq $frontendAppId } |
  Select-Object -First 1

if (-not $backendPreAuth) {
  throw "Backend app does not pre-authorize frontend appId $frontendAppId."
}

$matchingPreAuthScope = $backendPreAuth.delegatedPermissionIds |
  Where-Object { $_ -eq $backendScopeId } |
  Select-Object -First 1

if (-not $matchingPreAuthScope) {
  throw "Backend pre-authorization for frontend appId $frontendAppId does not include scope id $backendScopeId."
}

Write-Host "Tenant ID: $tenantId"
Write-Host "Backend appId: $backendAppId"
Write-Host "Frontend appId: $frontendAppId"
Write-Host "Backend scope ID: $backendScopeId"
Write-Host "Verification passed."
