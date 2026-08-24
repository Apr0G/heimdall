/**
 * Placeholder bundle. Terraform creates the function from this file so the
 * resource can exist before the real (dependency-bearing) bundle is built;
 * deploy-email-sender.yml replaces it via update-function-code. If this ever
 * runs in production the trigger was enabled before the bundle was deployed —
 * fail loudly so the misordering is obvious, never silently drop an invite.
 *
 * DO NOT EDIT: terraform tracks this file's hash; changing it after the real
 * bundle is live would make the next `terraform apply` revert the function to
 * the stub.
 */
export async function handler() {
  throw new Error(
    "cognito-email-sender bundle not deployed — run the deploy-email-sender workflow before enabling the trigger",
  );
}
