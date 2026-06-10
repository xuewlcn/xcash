from unittest.mock import patch

from django.test import SimpleTestCase

from common.decorators import singleton_task


class FakeCache:
    def __init__(self):
        self.values = {}
        self.last_key = ""
        self.deleted_keys = []

    def add(self, key, value, timeout):
        if key in self.values:
            return False
        self.values[key] = value
        self.last_key = key
        return True

    def get(self, key):
        return self.values.get(key)

    def delete(self, key):
        self.deleted_keys.append(key)
        self.values.pop(key, None)


class SingletonTaskTests(SimpleTestCase):
    def test_finally_does_not_delete_lock_owned_by_new_instance(self):
        fake_cache = FakeCache()

        @singleton_task(timeout=5)
        def task():
            fake_cache.values[fake_cache.last_key] = "new-owner"
            return "ok"

        with patch("common.decorators.cache", fake_cache):
            result = task()

        self.assertEqual(result, "ok")
        self.assertEqual(
            fake_cache.values[f"{task.__name__}-locked"],
            "new-owner",
        )
        self.assertEqual(fake_cache.deleted_keys, [])

    def test_finally_deletes_own_lock(self):
        fake_cache = FakeCache()

        @singleton_task(timeout=5)
        def task():
            return "ok"

        with patch("common.decorators.cache", fake_cache):
            result = task()

        self.assertEqual(result, "ok")
        self.assertNotIn(f"{task.__name__}-locked", fake_cache.values)
        self.assertEqual(fake_cache.deleted_keys, [f"{task.__name__}-locked"])
