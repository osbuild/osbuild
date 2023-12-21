"""
Mixin helper classes
"""


class MixinImmutableID:
    """
    Mixin to ensure that "self.id" attributes are immutable after id is set
    """

    def __setattr__(self, name, val):
        if hasattr(self, "id"):
            class_name = self.__class__.__name__
            raise ValueError(f"cannot set '{name}': {class_name} cannot be changed after creation")
        super().__setattr__(name, val)
