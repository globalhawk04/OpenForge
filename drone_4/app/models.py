##
# FILE: app/models.py
from sqlalchemy import (
    Column, Integer, String, Text, ForeignKey, JSON, Float, Boolean, DateTime, Enum
)
from sqlalchemy.orm import relationship
from app.database import Base
import datetime
import enum

class ProjectStatus(str, enum.Enum):
    INTAKE = "intake"
    SOURCING = "sourcing"
    VERIFYING = "verifying"
    SIMULATING = "simulating"
    GENERATING_CAD = "generating"
    COMPLETE = "complete"
    FAILED = "failed"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    
    projects = relationship("DroneProject", back_populates="owner", cascade="all, delete-orphan")
    components = relationship("Component", back_populates="owner", cascade="all, delete-orphan")

class DroneProject(Base):
    __tablename__ = "drone_projects"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    project_name = Column(String, default="Untitled Drone")
    user_prompt = Column(Text, nullable=False)
    constraints = Column(JSON, default=dict) # Budget, size, type
    
    status = Column(String, default=ProjectStatus.INTAKE, index=True)
    status_message = Column(String, nullable=True)
    
    # The Bill of Materials (List of Component IDs)
    bill_of_materials = Column(JSON, default=list) 
    
    physics_report = Column(JSON, nullable=True)
    
    cad_file_path = Column(String, nullable=True)
    stl_file_path = Column(String, nullable=True)
    assembly_guide_md = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.datetime.utcnow)

    owner = relationship("User", back_populates="projects")

class Component(Base):
    __tablename__ = "components"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    name = Column(String, index=True, nullable=False)
    category = Column(String, nullable=False, index=True) # frame, motor, esc...
    
    source_url = Column(String, nullable=False)
    price = Column(Float, nullable=True)
    image_url = Column(String, nullable=True)
    
    # Engineering Specs (e.g., {"mounting": "16x16", "kv": 2500})
    specs = Column(JSON, default=dict)
    
    is_verified = Column(Boolean, default=False)
    verification_notes = Column(Text, nullable=True)

    owner = relationship("User", back_populates="components")

class VisionExtractionQueue(Base):
    __tablename__ = "vision_extraction_queue"
    id = Column(Integer, primary_key=True, index=True)
    component_id = Column(Integer, ForeignKey("components.id"), nullable=False)
    image_url = Column(String, nullable=False)
    target_field = Column(String, nullable=True) 
    status = Column(String, default="pending")
    ai_extraction_result = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)