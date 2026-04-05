#!/bin/bash
source venv/bin/activate
uvicorn chat:app --reload