    def update_profile_list(self):
        """Update the profile combo box with available profiles."""
        try:
            if hasattr(self.parent_window, 'run_profile_widget'):
                profiles = self.parent_window.run_profile_widget.get_all_profiles()
                self.profile_combo.clear()
                for profile_name in profiles.keys():
                    self.profile_combo.addItem(profile_name)
                    
                if profiles:
                    self.update_scratch_disk_display()
        except Exception as e:
            print(f"Error updating profile list: {e}")
            
    def update_scratch_disk_display(self):
        """Update the scratch disk display based on selected profile."""
        try:
            profile_name = self.profile_combo.currentText()
            if hasattr(self.parent_window, 'run_profile_widget') and profile_name:
                profiles = self.parent_window.run_profile_widget.get_all_profiles()
                if profile_name in profiles:
                    fast_disk = profiles[profile_name].get('fast_scratch_disk', 'Not configured')
                    self.scratch_display.setText(fast_disk)
                else:
                    self.scratch_display.setText("Profile not found")
            else:
                self.scratch_display.setText("No profile selected")
        except Exception as e:
            self.scratch_display.setText(f"Error: {e}")
