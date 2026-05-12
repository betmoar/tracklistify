"""
Tests for Issue #12: Thread-Safe Singletons

Ensures all singleton patterns in the codebase are thread-safe.
"""

# Standard library imports
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed


# Local imports
from tracklistify.config.factory import get_config, clear_config
from tracklistify.cache.factory import get_cache
from tracklistify.utils.rate_limiter import get_global_rate_limiter
from tracklistify.providers.factory import create_provider_factory, clear_provider_cache


class TestConfigSingletonThreadSafety:
    """Test config singleton thread safety."""

    def setup_method(self):
        """Clear config before each test."""
        clear_config()

    def teardown_method(self):
        """Clear config after each test."""
        clear_config()

    def test_get_config_thread_safe(self):
        """Test that get_config returns same instance across threads."""
        instances = []
        errors = []

        def worker():
            try:
                config = get_config()
                instances.append(id(config))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors occurred: {errors}"
        # All threads should get same instance
        assert len(set(instances)) == 1, (
            f"Expected 1 unique instance, got {len(set(instances))}"
        )

    def test_get_config_concurrent_creation(self):
        """Test concurrent config creation doesn't create duplicates."""
        instances = []
        barrier = threading.Barrier(10)

        def worker():
            barrier.wait()  # All threads start at same time
            config = get_config()
            instances.append(id(config))

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have exactly one instance
        assert len(set(instances)) == 1


class TestCacheSingletonThreadSafety:
    """Test cache singleton thread safety."""

    def test_get_cache_thread_safe(self):
        """Test that get_cache returns same instance across threads."""
        instances = []
        errors = []

        def worker():
            try:
                cache = get_cache()
                instances.append(id(cache))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors occurred: {errors}"
        assert len(set(instances)) == 1, (
            f"Expected 1 unique instance, got {len(set(instances))}"
        )

    def test_get_cache_concurrent_initialization(self):
        """Test concurrent cache initialization is safe."""
        instances = []
        barrier = threading.Barrier(10)

        def worker():
            barrier.wait()
            cache = get_cache()
            instances.append(id(cache))

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(set(instances)) == 1


class TestRateLimiterSingletonThreadSafety:
    """Test rate limiter singleton thread safety."""

    def test_get_global_rate_limiter_thread_safe(self):
        """Test that get_global_rate_limiter returns same instance."""
        instances = []
        errors = []

        def worker():
            try:
                limiter = get_global_rate_limiter()
                instances.append(id(limiter))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors occurred: {errors}"
        assert len(set(instances)) == 1

    def test_rate_limiter_high_concurrency(self):
        """Test rate limiter under high concurrency."""
        instances = []

        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [
                executor.submit(lambda: id(get_global_rate_limiter()))
                for _ in range(100)
            ]
            for future in as_completed(futures):
                instances.append(future.result())

        assert len(set(instances)) == 1


class TestProviderFactorySingletonThreadSafety:
    """Test provider factory singleton thread safety."""

    def setup_method(self):
        """Clear provider cache before each test."""
        clear_provider_cache()

    def teardown_method(self):
        """Clear provider cache after each test."""
        clear_provider_cache()

    def test_create_provider_factory_thread_safe(self):
        """Test that create_provider_factory returns same instance."""
        instances = []
        errors = []

        def worker():
            try:
                factory = create_provider_factory()
                instances.append(id(factory))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors occurred: {errors}"
        assert len(set(instances)) == 1

    def test_provider_factory_concurrent_creation(self):
        """Test concurrent factory creation."""
        instances = []
        barrier = threading.Barrier(10)

        def worker():
            barrier.wait()
            factory = create_provider_factory()
            instances.append(id(factory))

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(set(instances)) == 1


class TestThreadSafetyStress:
    """Stress tests for thread safety."""

    def test_mixed_singleton_access(self):
        """Test accessing multiple singletons concurrently."""
        config_ids = []
        cache_ids = []
        limiter_ids = []
        errors = []

        def worker():
            try:
                config_ids.append(id(get_config()))
                cache_ids.append(id(get_cache()))
                limiter_ids.append(id(get_global_rate_limiter()))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors occurred: {errors}"
        assert len(set(config_ids)) == 1
        assert len(set(cache_ids)) == 1
        assert len(set(limiter_ids)) == 1

    def test_rapid_singleton_access(self):
        """Test rapid sequential singleton access."""
        for _ in range(1000):
            get_config()
            get_cache()
            get_global_rate_limiter()

        # Should not raise any exceptions


class TestLockImplementation:
    """Test that locks are properly implemented."""

    def test_config_factory_has_lock(self):
        """Test ConfigFactory uses thread-safe mechanism."""
        import inspect
        from tracklistify.config import factory as config_factory

        source = inspect.getsource(config_factory)
        # Should have either Lock or lru_cache for thread safety
        assert "Lock" in source or "lru_cache" in source or "_lock" in source, (
            "ConfigFactory should use Lock or lru_cache for thread safety"
        )

    def test_cache_factory_has_lock(self):
        """Test cache factory uses thread-safe mechanism."""
        import inspect
        from tracklistify.cache import factory as cache_factory

        source = inspect.getsource(cache_factory)
        assert "Lock" in source or "lru_cache" in source or "_lock" in source, (
            "Cache factory should use Lock or lru_cache for thread safety"
        )

    def test_rate_limiter_has_lock(self):
        """Test rate limiter factory uses thread-safe mechanism."""
        import inspect
        from tracklistify.utils import rate_limiter

        inspect.getsource(rate_limiter.get_global_rate_limiter)
        # Check if it has thread-safety mechanism
        module_source = inspect.getsource(rate_limiter)
        assert "Lock" in module_source or "lru_cache" in module_source, (
            "Rate limiter should use Lock or lru_cache for thread safety"
        )

    def test_provider_factory_has_lock(self):
        """Test provider factory uses thread-safe mechanism."""
        import inspect
        from tracklistify.providers import factory as provider_factory

        source = inspect.getsource(provider_factory)
        assert "Lock" in source or "lru_cache" in source or "_lock" in source, (
            "Provider factory should use Lock or lru_cache for thread safety"
        )
