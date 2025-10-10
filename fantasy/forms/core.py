from django import forms
from django.contrib.auth.forms import UserCreationForm
from ..models import User


class UserRegistrationForm(UserCreationForm):
    """Form for user registration with custom User model"""

    email = forms.EmailField(required=False)
    display_name = forms.CharField(max_length=100, required=False)

    class Meta:
        model = User
        fields = ("username", "email", "display_name", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].help_text = "Will be used for login and URL generation"
        self.fields["display_name"].help_text = "Optional friendly name for display"

        # Add CSS classes to fields
        for field in self.fields.values():
            field.widget.attrs.update({"class": "form-control"})


class UserProfileForm(forms.ModelForm):
    """Form for updating user profile"""

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "display_name"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({"class": "form-control"})
