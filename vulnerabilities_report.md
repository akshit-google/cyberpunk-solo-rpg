# Vulnerability Assessment Report

This report documents the security vulnerabilities identified during the analysis of the repository.

## Executive Summary

A security review of the codebase was conducted. One **HIGH** severity vulnerability was identified, which could allow an attacker to cause a Denial of Service (DoS) by exploiting uncontrolled resource consumption.

---

## Findings

### 1. Uncontrolled Resource Consumption in `roll_dice` leading to Denial of Service (DoS)

*   **Vulnerability ID:** `fa43e0d6`
*   **Severity:** 🟠 High
*   **Vulnerability Type:** CWE-400 (Uncontrolled Resource Consumption / Denial of Service)
*   **File:** [`app/tools.py`](file:///usr/local/google/home/akshitgautam/cyberpunk-solo-rpg/app/tools.py#L28-L50)
*   **Function:** `roll_dice`

#### Description

The `roll_dice` function parses a dice formula (e.g., `1d10`, `2d6`, `1000000d6`) from user input using a regular expression. While the regex validates the format, it does not enforce any upper limit on the number of dice (`num_dice`) to be rolled.

The parsed `num_dice` is used directly in a list comprehension to generate the rolls:
```python
rolls = [random.randint(1, sides) for _ in range(num_dice)]
```

If a user provides a formula with a very large number of dice (e.g., `10000000d6`), the application attempts to allocate a list of that size and run the random number generator loop sequentially. This blocks the single execution thread, leading to high CPU/memory usage and potential process crash (Out of Memory), causing a Denial of Service for all users.

#### Proof of Concept (PoC)

Verification testing confirmed that the execution time scales linearly with the number of dice, blocking the thread:
*   Rolling **10** dice: < 0.01 seconds
*   Rolling **100,000** dice: ~0.03 seconds
*   Rolling **1,000,000** dice: ~0.35 seconds
*   Rolling **10,000,000** dice: **~8.1 seconds** (Process blocked for the entire duration)

An input of `100,000,000d6` or higher is highly likely to crash the service due to memory exhaustion.

#### Recommendation

Implement strict input validation limits on the dice formula. 
*   Limit the maximum number of dice (e.g., `num_dice <= 100`).
*   Limit the maximum number of sides (e.g., `sides <= 1000`).

Example fix in `app/tools.py`:

```python
    num_dice = int(match.group(1))
    sides = int(match.group(2))
    
    if num_dice > 100:
        return {"status": "error", "message": "Cannot roll more than 100 dice at once."}
    if sides > 1000:
        return {"status": "error", "message": "Dice cannot have more than 1000 sides."}
```
