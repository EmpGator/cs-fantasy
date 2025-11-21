from ..models import SwissModule, StatPredictionsModule, Bracket
from .bracket import BracketPredictionForm
from .swiss import SwissModuleForm
from .stat_predictions import StatPredictionForm


class ModuleFormRegistry:
    """
    Registry for mapping module types to their corresponding form classes.

    This allows for extensible module types without modifying core code.
    New module types can be registered by adding them to the _registry dict
    or by calling the register() method.
    """

    _registry = {
        SwissModule: SwissModuleForm,
        StatPredictionsModule: StatPredictionForm,
        Bracket: BracketPredictionForm,
    }

    @classmethod
    def get_form_class(cls, module):
        """
        Get the appropriate form class for a module.

        Args:
            module: The module instance (SwissModule, etc.)

        Returns:
            class: The form class for this module type

        Raises:
            ValueError: If no form is registered for the module type
        """
        module_type = module.__class__
        form_class = cls._registry.get(module_type)

        if not form_class:
            raise ValueError(
                f"No form registered for module type: {module_type.__name__}. "
                f"Available types: {', '.join(m.__name__ for m in cls._registry.keys())}"
            )

        return form_class

    @classmethod
    def register(cls, module_type, form_class):
        """
        Register a new module type -> form class mapping.

        Args:
            module_type (str): The name of the module class (e.g., "SwissModule")
            form_class (class): The form class to use for this module type

        Example:
            ModuleFormRegistry.register("CustomModule", CustomModuleForm)
        """
        cls._registry[module_type] = form_class

    @classmethod
    def unregister(cls, module_type):
        """
        Remove a module type from the registry.

        Args:
            module_type (str): The name of the module class to unregister
        """
        if module_type in cls._registry:
            del cls._registry[module_type]

    @classmethod
    def get_registered_types(cls):
        """
        Get a list of all registered module types.

        Returns:
            list: List of registered module type names
        """
        return list(cls._registry.keys())

    @classmethod
    def is_registered(cls, module_type):
        """
        Check if a module type is registered.

        Args:
            module_type (str): The name of the module class

        Returns:
            bool: True if registered, False otherwise
        """
        return module_type in cls._registry


def create_module_form(module, user, *args, **kwargs):
    """
    Factory function to create the appropriate form for a module.

    This is the main entry point for creating module forms.
    It automatically selects the correct form class based on the module type.

    Args:
        module: The module instance (SwissModule, etc.)
        user: The User making predictions
        *args: Additional positional arguments to pass to the form
        **kwargs: Additional keyword arguments to pass to the form

    Returns:
        BaseModuleForm: An instance of the appropriate form class

    Raises:
        ValueError: If no form is registered for the module type

    Example:
        form = create_module_form(swiss_module, user, prefix='module_1')
    """
    form_class = ModuleFormRegistry.get_form_class(module)
    return form_class(module, user, *args, **kwargs)
