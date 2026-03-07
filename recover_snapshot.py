import os
import sys
import shutil
import datetime
from pathlib import Path
import inquirer
from inquirer.themes import GreenPassion

def get_snapshots(snapshot_dir):
    """Get all available snapshots sorted by creation time (newest first)"""
    if not os.path.exists(snapshot_dir):
        print(f"No snapshots directory found at {snapshot_dir}")
        return []
    
    snapshots = []
    for item in os.listdir(snapshot_dir):
        item_path = os.path.join(snapshot_dir, item)
        if os.path.isdir(item_path):
            try:
                # Get creation time and format it
                creation_time = datetime.datetime.fromtimestamp(os.path.getctime(item_path))
                time_str = creation_time.strftime("%Y-%m-%d %H:%M:%S")
                snapshots.append({
                    'name': f"{item} ({time_str})",
                    'value': item_path,
                    'creation_time': creation_time
                })
            except Exception as e:
                print(f"Error processing {item}: {e}")
    
    # Sort by creation time (newest first)
    return sorted(snapshots, key=lambda x: x['creation_time'], reverse=True)

def count_files(directory):
    """Count files in a directory recursively"""
    count = 0
    for root, dirs, files in os.walk(directory):
        count += len(files)
    return count

def restore_snapshot(snapshot_path, project_root):
    """Restore files from a snapshot to the project"""
    print(f"\nRestoring from: {os.path.basename(snapshot_path)}")
    print(f"To: {project_root}\n")
    
    # Count files to restore
    file_count = count_files(snapshot_path)
    print(f"Files to restore: {file_count}")
    
    # Confirm restoration
    questions = [
        inquirer.Confirm('confirm',
                        message=f"Are you sure you want to restore these {file_count} files? This will overwrite existing files.",
                        default=False),
    ]
    answers = inquirer.prompt(questions, theme=GreenPassion())
    
    if not answers or not answers['confirm']:
        print("Restoration cancelled.")
        return False
    
    # Restore files
    files_restored = 0
    for root, dirs, files in os.walk(snapshot_path):
        # Calculate relative path
        rel_path = os.path.relpath(root, snapshot_path)
        
        # Create target directory if it doesn't exist
        if rel_path == '.':
            target_dir = project_root
        else:
            target_dir = os.path.join(project_root, rel_path)
            os.makedirs(target_dir, exist_ok=True)
        
        # Copy files
        for file in files:
            # Skip the snapshot info file
            if file == '_SNAPSHOT_INFO.txt':
                continue
                
            source_file = os.path.join(root, file)
            target_file = os.path.join(target_dir, file)
            
            try:
                shutil.copy2(source_file, target_file)
                files_restored += 1
                print(f"Restored: {os.path.relpath(target_file, project_root)}")
            except Exception as e:
                print(f"Error restoring {source_file}: {e}")
    
    print(f"\nRestoration complete! {files_restored} files restored.")
    return True

def main():
    # Get project root directory
    script_path = Path(os.path.abspath(__file__))
    project_root = script_path.parent
    
    # Get snapshots directory
    snapshots_dir = os.path.join(project_root, '.snapshots')
    
    # Get available snapshots
    snapshots = get_snapshots(snapshots_dir)
    
    if not snapshots:
        print("No snapshots available to restore.")
        return
    
    # Ask user which snapshot to restore
    questions = [
        inquirer.List('snapshot',
                      message="Select a snapshot to restore:",
                      choices=[s['name'] for s in snapshots],
                      carousel=True),
    ]
    
    answers = inquirer.prompt(questions, theme=GreenPassion())
    
    if not answers:
        print("No snapshot selected. Exiting.")
        return
    
    # Find the selected snapshot
    selected_name = answers['snapshot']
    selected_snapshot = next((s['value'] for s in snapshots if s['name'] == selected_name), None)
    
    if selected_snapshot:
        restore_snapshot(selected_snapshot, project_root)
    else:
        print("Error: Selected snapshot not found.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
    except Exception as e:
        print(f"\nError: {e}")
    
    # Keep console open
    input("\nPress Enter to exit...")
