#!/bin/bash

# Format all HTML files in the project using djlint
echo "Formatting HTML files with djlint..."

# Find and format all HTML files
find templates -name "*.html" -type f | while read -r file; do
    echo "Formatting: $file"
    djlint --reformat "$file"
done

echo "HTML formatting complete!"
