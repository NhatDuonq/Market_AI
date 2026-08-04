"""
Retry decorator với exponential backoff cho các hàm scraping.
Xử lý HTTP 403, 429, Timeout → retry sau delay tăng dần.
"""
import time
import random
import functools


def retry(max_attempts: int = 3, backoff_factor: float = 2.0, exceptions: tuple = (Exception,)):
    """
    Decorator retry với exponential backoff.
    
    Args:
        max_attempts: Số lần thử tối đa.
        backoff_factor: Hệ số nhân delay giữa các lần retry (1s → 2s → 4s).
        exceptions: Tuple các exception types được retry.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        delay = backoff_factor ** (attempt - 1) + random.uniform(0.1, 0.5)
                        print(f"[Retry] ⚠️ {func.__name__}() lần {attempt}/{max_attempts} thất bại: {e}")
                        print(f"[Retry] ⏳ Chờ {delay:.1f}s trước lần thử tiếp theo...")
                        time.sleep(delay)
                    else:
                        print(f"[Retry] ❌ {func.__name__}() thất bại sau {max_attempts} lần thử: {e}")
            raise last_exception
        return wrapper
    return decorator


# Pool User-Agent để rotate mỗi lần request
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 OPR/109.0.0.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]


def get_random_user_agent() -> str:
    """Trả về User-Agent ngẫu nhiên từ pool."""
    return random.choice(USER_AGENTS)


def random_delay(min_seconds: float = 1.5, max_seconds: float = 4.0):
    """Tạo delay ngẫu nhiên để tránh pattern detection."""
    delay = random.uniform(min_seconds, max_seconds)
    time.sleep(delay)
    return delay
