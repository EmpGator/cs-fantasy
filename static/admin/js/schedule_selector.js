/**
 * Schedule task selector enhancement
 * Auto-populates the func field when a task is selected from the dropdown
 */
(function() {
    'use strict';

    document.addEventListener('DOMContentLoaded', function() {
        const taskSelector = document.getElementById('id_task_selector');
        const funcField = document.getElementById('id_func');

        if (!taskSelector || !funcField) {
            return;
        }

        // Auto-populate func field when task is selected
        taskSelector.addEventListener('change', function() {
            const selectedTask = this.value;
            if (selectedTask) {
                funcField.value = selectedTask;
            }
        });

        // Make func field readonly when a common task is selected
        // This prevents accidental modifications
        taskSelector.addEventListener('change', function() {
            if (this.value) {
                funcField.setAttribute('readonly', 'readonly');
                funcField.style.backgroundColor = '#f0f0f0';
            } else {
                funcField.removeAttribute('readonly');
                funcField.style.backgroundColor = '';
            }
        });

        // Initialize readonly state if a common task is already selected
        if (taskSelector.value) {
            funcField.setAttribute('readonly', 'readonly');
            funcField.style.backgroundColor = '#f0f0f0';
        }
    });
})();
