# Contributing Guide

## 1. Work in Feature Branches

All development should be done in separate branches, not directly in `main`.

Create a branch from the latest `main`:

```bash
git checkout main
git pull origin main
git checkout -b <branch-name>
```

Make your changes, commit them, and push the branch to the repository:

```bash
git add .
git commit -m "Short description of changes"
git push origin <branch-name>
```

This will create the same branch on the remote repository.

## 2. Branch Naming Convention

Branch names should follow the pattern:

```bash
type/short-description
```

Examples:

```bash
feature/anomaly-a-going-dark
feature/anomaly-c-draft-change
feature/anomaly-d-identity-cloning
data/add-sample-ais-dataset
data/update-test-csv
fix/distance-calculation
refactor/worker-aggregation
```

Common prefixes:

```bash
feature    # new functionality
fix        # bug fixes
data       # dataset changes
refactor   # code restructuring without behavior change
docs       # documentation updates
```

Use kebab-case for the description part.

## 3. Creating a Pull Request

After pushing your branch, create a Pull Request (PR) on GitHub to merge it into main.

Before creating the PR:
- ensure the branch is up to date with main
- check that only relevant files are included

## 4. Labels

Each PR should include an appropriate label.

Common labels used in this project:

```bash
enhancement   # new features or improvements
bug           # bug fixes
documentation # documentation updates
```

Use the label that best describes the type of change.

## 5. Code Review

If the change is significant or affects core functionality, a reviewer can be assigned in the PR, although for this project it is not mandatory.

Examples of changes that may require review:
- new anomaly detection logic
- major refactoring
- changes affecting multiple modules
- algorithm or metric changes

Small changes, such as minor data updates or documentation fixes, do not require a reviewer.

## 6. Merging

Once the Pull Request is approved, or if review is not required:
- merge the PR into main
- ensure there are no conflicts

## 7. Deleting Branches

After the PR is merged, the branch should be deleted from the remote repository to keep the repository clean.

GitHub usually provides a Delete branch button after merging.

Optionally, delete the local branch as well:

```bash
git branch -d <branch-name>
```

## 8. Keep Your Local Repository Updated

Before starting new work:

```bash
git checkout main
git pull origin main
```

Then create a new branch for the next task.


## 9. Code Style and Documentation

### Type Hints

Use type hints whenever possible, especially in function and method definitions.

Example:

```python
def calculate_distance(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float
) -> float:
    ...
```    
    
Type hints improve readability, help static analysis tools, and make the code easier to maintain.

### Docstrings

Important functions, classes, and methods should include docstrings.

Docstrings should follow the Google Python Style Guide format.

Example:

```python
def calculate_distance(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Calculate the great-circle distance between two geographic points
    using the Haversine formula.

    Args:
        lat1: Latitude of the first point in decimal degrees.
        lon1: Longitude of the first point in decimal degrees.
        lat2: Latitude of the second point in decimal degrees.
        lon2: Longitude of the second point in decimal degrees.

    Returns:
        Distance between the two points in kilometers.
    """
    ...
```

### Constants

Global constants should follow these rules:
- Constants must be written in UPPER_CASE
- Constants should be defined after imports at the top of the file, or
- Shared configuration values should be moved to a dedicated `config.py` module.

Example:
```python
MAX_AIS_GAP_HOURS = 4
MAX_TRANSFER_DISTANCE_METERS = 500
MIN_LOITERING_TIME_HOURS = 2
```
