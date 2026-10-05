from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(
        min_length=1,
    )

    # Signs login tokens; must be long enough to be hard to guess.
    secret_key: str = Field(
        min_length=32,
    )

    access_token_expire_minutes: int = Field(
        default=60,
        gt=0,
    )

    # Per-user limits on the assistant endpoints (each call costs money).
    assistant_requests_per_minute: int = Field(
        default=10,
        gt=0,
    )

    assistant_requests_per_day: int = Field(
        default=300,
        gt=0,
    )

    # Where the web app runs, for the links in emails.
    frontend_url: str = "http://localhost:5173"

    # How emails are sent: "console" prints them in the server's log (for
    # development: click the link there); "smtp" sends them for real with
    # the settings below; "brevo" sends them through Brevo's HTTPS API
    # (for hosts that block the SMTP ports).
    email_backend: str = Field(
        default="console",
        pattern="^(console|smtp|brevo)$",
    )
    brevo_api_key: str | None = None
    email_from: str = "TellSpend <no-reply@tellspend.local>"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    # STARTTLS on the usual submission port; turn off only for a local
    # test server.
    smtp_starttls: bool = True

    # How long a verification code and a reset link work, and how many
    # wrong tries a code allows.
    verify_code_minutes: int = Field(default=15, gt=0)
    verify_code_attempts: int = Field(default=5, gt=0)
    reset_password_minutes: int = Field(default=60, gt=0)
    # The shortest time between two emails of the same kind to one user.
    email_resend_seconds: int = Field(default=60, ge=0)

    llm_model: str | None = None

    llm_base_url: str | None = None

    llm_api_key: str | None = None

    # How long one model call may take before it's abandoned and, if
    # attempts remain, tried again. Attempts x timeout must stay below
    # what the browser waits for a read (90 seconds).
    llm_timeout_seconds: float = Field(
        default=40,
        gt=0,
    )

    # How many times one read may ask the model (1 = no retry).
    llm_attempts: int = Field(
        default=2,
        ge=1,
        le=3,
    )

    # How much the model's answers may vary between calls. 0 reads the
    # same message the same way every time.
    llm_temperature: float = Field(
        default=0,
        ge=0,
        le=2,
    )

    # OpenRouter only: which of a model's hosts to prefer. "throughput"
    # is the fastest; "price" the cheapest; "latency" the quickest start.
    llm_provider_sort: str = "throughput"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()