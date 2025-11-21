from abc import ABCMeta, abstractmethod
from django import forms


class ModuleFormMeta(forms.forms.DeclarativeFieldsMetaclass, ABCMeta):
    """Combined metaclass for BaseModuleForm to support both Django forms and ABC"""

    pass


class BaseModuleForm(forms.Form, metaclass=ModuleFormMeta):
    """
    Abstract base class for all module prediction forms.

    Each module type (Swiss, Single Elimination, etc.) should extend this class
    and implement the abstract methods to define its specific behavior.
    """

    def __init__(self, module, user, *args, **kwargs):
        """
        Initialize the form with module and user context.

        Args:
            module: The module instance (SwissModule, etc.)
            user: The User making predictions
        """
        super().__init__(*args, **kwargs)
        self.module = module
        self.user = user
        self._build_form_fields()
        self._load_existing_predictions()

    @abstractmethod
    def _build_form_fields(self):
        """
        Build form fields specific to this module type.

        This method should create all necessary fields in self.fields
        based on the module's structure (teams, matches, etc.)
        """
        pass

    @abstractmethod
    def _load_existing_predictions(self):
        """
        Load existing predictions for this module and populate initial data.

        This method should query the database for existing predictions
        and set self.initial values accordingly.
        """
        pass

    @abstractmethod
    def save(self):
        """
        Save the predictions from this form.

        This method should:
        1. Validate the form if not already validated
        2. Clear existing predictions for this module/user
        3. Create new predictions based on cleaned_data

        Returns:
            bool: True if save was successful, False otherwise
        """
        pass

    def get_validation_context(self):
        """
        Return context data for template rendering and validation feedback.

        Returns:
            dict: Context data including errors, usage counts, etc.
        """
        return {
            "form_errors": self.errors,
            "is_valid": self.is_valid() if self.is_bound else None,
            "module": self.module,
        }
