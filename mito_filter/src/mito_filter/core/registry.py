"""Generic type-safe registry + ``@register`` decorators.

Domain-free. Every pluggable component (field provider, candidate source, feature
extractor, constraint, dataset, optimizer) is a class registered under a string name and
instantiated from YAML config. This module is **fully implemented** — downstream modules
depend on it at import time.

Example:
    >>> reg: Registry[int] = Registry("things")
    >>> @reg.register("answer")
    ... class Answer:
    ...     pass
    >>> reg.get("answer") is Answer
    True
"""

from __future__ import annotations

from typing import Callable, Dict, Generic, Iterator, List, Tuple, Type, TypeVar

T = TypeVar("T")


class Registry(Generic[T]):
    """A named map ``str -> class`` with a decorator API.

    Args:
        kind: Human-readable label for this registry (used in error messages).

    Attributes:
        kind: The registry label.
    """

    def __init__(self, kind: str) -> None:
        self.kind: str = kind
        self._entries: Dict[str, Type[T]] = {}

    def register(self, name: str) -> Callable[[Type[T]], Type[T]]:
        """Return a class decorator that registers the class under ``name``.

        Args:
            name: The lookup key. Must be unique within this registry.

        Returns:
            A decorator that records the class and returns it unchanged.

        Raises:
            ValueError: If ``name`` is already registered.
        """

        def _decorator(cls: Type[T]) -> Type[T]:
            if name in self._entries:
                raise ValueError(f"{self.kind}: name '{name}' already registered")
            self._entries[name] = cls
            return cls

        return _decorator

    def register_class(self, name: str, cls: Type[T]) -> None:
        """Register ``cls`` under ``name`` imperatively (non-decorator form).

        Args:
            name: The lookup key. Must be unique within this registry.
            cls: The class to register.

        Raises:
            ValueError: If ``name`` is already registered.
        """
        if name in self._entries:
            raise ValueError(f"{self.kind}: name '{name}' already registered")
        self._entries[name] = cls

    def get(self, name: str) -> Type[T]:
        """Look up a registered class by name.

        Args:
            name: The lookup key.

        Returns:
            The registered class.

        Raises:
            KeyError: If ``name`` is not registered (message lists known names).
        """
        try:
            return self._entries[name]
        except KeyError:
            known = ", ".join(sorted(self._entries)) or "<none>"
            raise KeyError(f"{self.kind}: unknown name '{name}'. Known: {known}") from None

    def create(self, name: str, **kwargs: object) -> T:
        """Instantiate a registered class with keyword arguments (the YAML path).

        Args:
            name: The lookup key.
            **kwargs: Constructor keyword arguments (typically a YAML stanza).

        Returns:
            A new instance of the registered class.
        """
        return self.get(name)(**kwargs)

    def names(self) -> List[str]:
        """Return the sorted list of registered names."""
        return sorted(self._entries)

    def __contains__(self, name: object) -> bool:
        return name in self._entries

    def __iter__(self) -> Iterator[Tuple[str, Type[T]]]:
        return iter(self._entries.items())

    def __len__(self) -> int:
        return len(self._entries)
