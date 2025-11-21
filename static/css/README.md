# FantasyGator - Navy Blue Dark Theme

## Overview

This is a custom dark theme for the FantasyGator application, featuring a navy blue color scheme with excellent readability and modern aesthetics. The theme uses Bootstrap 5's CSS custom properties for easy customization and maintainability.

## Color Palette

### Primary Background Colors
- **Main Background**: `#0a1929` - Very dark navy, used for body background
- **Secondary Background**: `#0f1e2e` - Deep navy for navbar and footer
- **Card/Component Background**: `#1a2942` - Navy-grey for cards and elevated surfaces
- **Elevated Elements**: `#243550` - Lighter navy for hover states and focused inputs

### Text Colors
- **Primary Text**: `#e3e8ef` - Cool light grey for body text
- **Emphasis Text**: `#f1f5f9` - Brightest text for headings
- **Secondary Text**: `#b8c5d6` - Muted for secondary information
- **Muted Text**: `#94a3b8` - Subtle grey for less important text

### Accent Colors
- **Primary (Blue)**: `#2196f3` - Material Design blue for primary actions
- **Success (Green)**: `#10b981` - Emerald green for success states
- **Warning (Amber)**: `#f59e0b` - Amber for warnings
- **Danger (Red)**: `#ef4444` - Red for errors and destructive actions
- **Info (Cyan)**: `#06b6d4` - Cyan for informational messages

### UI Elements
- **Links**: `#60a5fa` - Light blue for links
- **Link Hover**: `#93c5fd` - Lighter blue for link hover
- **Borders**: `#2d3e50` - Navy-grey for borders

## How Bootstrap Theming Works

### CSS Custom Properties
Bootstrap 5 uses CSS Custom Properties (CSS Variables), which makes theming straightforward. Instead of recompiling SASS, we can override variables at the `:root` level in CSS.

Example:
```css
:root {
    --bs-body-bg: #0a1929;
    --bs-body-color: #e3e8ef;
    --bs-primary: #2196f3;
}
```

These variables cascade throughout the application and affect all Bootstrap components automatically.

### Component-Specific Variables
Many Bootstrap components have their own scoped variables:
- Forms: `--bs-form-control-bg`, `--bs-form-control-color`
- Tables: `--bs-table-bg`, `--bs-table-striped-bg`
- Cards: `--bs-card-bg`, `--bs-card-border-color`

## File Structure

```
static/css/
├── theme.css          # Main theme file
└── README.md          # This documentation
```

## Theme Organization

The `theme.css` file is organized into logical sections:

1. **CSS Custom Properties** - Bootstrap variable overrides
2. **Base Styles** - Body and fundamental styles
3. **Typography** - Text, headings, and font styles
4. **Navigation** - Navbar styling
5. **Cards** - Card component styles
6. **Tables** - Table and data display styles
7. **Forms** - Form controls and inputs
8. **Buttons** - Button styles
9. **Alerts** - Alert message styles
10. **Badges** - Badge component styles
11. **Drag & Drop** - Custom styles for Swiss predictions
12. **Footer** - Footer styling
13. **Breadcrumbs** - Navigation breadcrumb styles
14. **Loading States** - HTMX loading indicators
15. **Utility Classes** - Helper classes
16. **Shadows** - Box shadow utilities
17. **Scrollbar Styling** - Custom scrollbar (optional)
18. **Responsive Adjustments** - Mobile-specific styles

## Customization

### Changing the Color Scheme

To modify colors, edit the CSS custom properties in the `:root` section:

```css
:root {
    --bs-body-bg: #your-color;
    --bs-primary: #your-color;
    /* etc. */
}
```

### Alternative Color Schemes

#### Charcoal with Teal
```css
--bs-body-bg: #1a1d23;
--bs-tertiary-bg: #2a2e35;
--bs-primary: #14b8a6;
--bs-border-color: #3a3e45;
```

#### Deep Purple-Blue
```css
--bs-body-bg: #1e1b30;
--bs-tertiary-bg: #2d2945;
--bs-primary: #6366f1;
--bs-border-color: #3d3a50;
```

### Adding Custom Styles

Add new styles at the end of `theme.css` or create a new CSS file and load it after `theme.css` in `base.html`:

```html
<link rel="stylesheet" href="{% static 'css/theme.css' %}" />
<link rel="stylesheet" href="{% static 'css/custom.css' %}" />
```

## Usage

The theme is automatically applied to all templates that extend `base.html`. No additional configuration is needed for individual pages.

### Admin Views
Django admin pages use their built-in theme and are not affected by this custom theme.

### New Components
When adding new components:
1. Use Bootstrap utility classes when possible
2. Leverage CSS custom properties for colors
3. Add component-specific styles to `theme.css` in the appropriate section

## Browser Compatibility

This theme uses CSS Custom Properties, which are supported by:
- Chrome/Edge 49+
- Firefox 31+
- Safari 9.1+
- iOS Safari 9.3+
- Android Browser 76+

Legacy browser support requires a fallback or polyfill.

## Maintenance

### Best Practices
1. Keep all theme-related styles in `theme.css`
2. Avoid inline styles in templates
3. Use CSS custom properties for consistency
4. Comment sections clearly
5. Test changes across all pages

### Performance
- Single CSS file minimizes HTTP requests
- Leverage browser caching
- Consider minification for production

## Testing

After making changes to the theme:
1. Clear browser cache
2. Run Django's development server: `python manage.py runserver`
3. Test all pages:
   - Home page
   - Tournament submissions
   - Swiss predictions
   - Forms and inputs
   - Tables
   - Alerts and messages
4. Test responsive design on mobile devices

## Contributing

When modifying the theme:
1. Test on all major pages
2. Ensure color contrast meets WCAG AA standards (4.5:1 for normal text)
3. Update this README if adding new sections or features
4. Keep the theme cohesive and consistent

## Resources

- [Bootstrap 5 Documentation](https://getbootstrap.com/docs/5.3/)
- [CSS Custom Properties Guide](https://developer.mozilla.org/en-US/docs/Web/CSS/Using_CSS_custom_properties)
- [Color Contrast Checker](https://webaim.org/resources/contrastchecker/)
