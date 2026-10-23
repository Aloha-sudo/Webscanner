from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://scanner:scanner@postgres:5432/scanner"
    REDIS_URL: str = "redis://redis:6379/0"
    MINIO_URL: str = "minio:9000"
    MINIO_USER: str = "minioadmin"
    MINIO_PASSWORD: str = "minioadmin"
    MINIO_BUCKET: str = "screenshots"
    MINIO_SECURE: bool = False
    APP_NAME: str = "WebScanner"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True
    SCANS_DIR: str = "/scans"
    MASSCAN_RATE: int = 100
    RUSTSCAN_TIMEOUT: int = 900
    NMAP_TIMEOUT: int = 600
    HTTX_TIMEOUT: int = 300
    GOWITNESS_TIMEOUT: int = 300

    # Профили портов
    PORT_PROFILES: dict = {
        # Базовые TCP-сервисы, службы AD и распространённые панели управления
        "quick": "21,22,23,25,53,80,88,110,111,135,139,143,389,443,445,464,636,993,995,1723,3268,3269,3306,3389,5900,5985,5986,8006,8080,8443,9389",

        # Все веб-порты (http/https/proxy/панели)
        "web": (
            "80,81,443,591,593,832,981,1010,1311,2082,2087,2095,2096,2480,3000,3128,"
            "3333,4243,4567,4711,4712,4993,5000,5104,5108,5280,5281,5555,5800,5801,"
            "5802,5900,5901,6082,6443,7001,7002,7396,7474,7547,8000,8001,8006,8008,8009,"
            "8010,8042,8069,8080,8081,8088,8090,8091,8118,8123,8172,8180,8200,8222,"
            "8243,8280,8281,8300,8333,8443,8447,8500,8800,8834,8880,8888,8983,9000,"
            "9001,9002,9003,9043,9060,9080,9090,9091,9092,9100,9200,9443,9800,9981,"
            "9982,9983,9984,9985,9986,9987,9988,9989,9990,9991,9992,9993,9994,9995,"
            "9996,9997,9998,9999,10000,10250,10443,28017"
        ),

        # Top-1000 nmap (спец-обработка, не список)
        "top100": None,
        "top1000": None,

        # Все 65535 портов
        "full": "1-65535",

        # Пользовательский — из payload.ports
        "custom": None,
    }

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
