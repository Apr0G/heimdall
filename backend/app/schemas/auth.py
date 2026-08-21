from uuid import UUID

from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    # email is whatever the user types; Cognito is the source of truth for validity.
    email: str
    password: str


class MfaChallenge(BaseModel):
    # "SOFTWARE_TOKEN_MFA" (enter a code) | "MFA_SETUP" (enroll a TOTP device first)
    # | "NEW_PASSWORD_REQUIRED" (temporary password: choose a real one first).
    # Named for its original MFA-only role; the field name `mfa` on LoginResponse is
    # kept so the frontend contract doesn't churn.
    challenge: str
    session: str  # opaque Cognito session to carry into the next auth-step call


class LoginResponse(BaseModel):
    # Exactly one of these is populated: tokens when login is complete, or `mfa`
    # when a TOTP challenge must be answered next. id_token is intentionally omitted
    # (the frontend never uses it — minimum-necessary).
    access_token: str | None = None
    token_type: str = "Bearer"
    expires_in: int | None = None
    mfa: MfaChallenge | None = None


class MfaVerifyRequest(BaseModel):
    email: str
    session: str
    code: str


class SetPasswordRequest(BaseModel):
    email: str
    session: str
    new_password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    email: str
    code: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    code: str  # current TOTP — both factors are re-checked before the change


class MfaRecoverStartRequest(BaseModel):
    email: str
    password: str


class MfaRecoverCompleteRequest(BaseModel):
    email: str
    password: str
    code: str  # the emailed one-time code


class MfaSetupStartRequest(BaseModel):
    email: str
    session: str


class MfaSetupStartResponse(BaseModel):
    secret: str  # base32 TOTP secret; the client renders the enrollment QR from it
    session: str


class MfaSetupCompleteRequest(BaseModel):
    email: str
    session: str
    code: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str | None
    role: str
    practice_id: UUID
