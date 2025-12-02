# FILE: app/services/isaac_service.py
import os
import math
import numpy as np
import trimesh

# Robust import for Isaac Sim libraries
try:
    from pxr import Usd, UsdGeom, UsdPhysics, UsdShade, Sdf, Gf, Vt
except ImportError:
    Usd = None
    print("⚠️  WARNING: 'pxr' library not found. Isaac USD generation will be skipped.")

ASSETS_DIR = os.path.abspath("output") 
USD_EXPORT_DIR = os.path.abspath("usd_export")
os.makedirs(USD_EXPORT_DIR, exist_ok=True)

class IsaacService:
    def __init__(self):
        pass

    def generate_robot_usd(self, robot_data):
        if Usd is None: return None

        sku = robot_data.get('sku_id', 'robot_dog')
        stage_path = os.path.join(USD_EXPORT_DIR, f"{sku}.usda")
        
        if os.path.exists(stage_path): os.remove(stage_path)
        stage = Usd.Stage.CreateNew(stage_path)
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z) 
        UsdGeom.SetStageMetersPerUnit(stage, 1.0) 

        # 1. Define Root (Articulation)
        root_path = f"/{sku.replace('-', '_')}"
        root_prim = UsdGeom.Xform.Define(stage, root_path)
        stage.SetDefaultPrim(root_prim.GetPrim())
        
        # Apply Articulation Root API to the top-level Xform
        UsdPhysics.ArticulationRootAPI.Apply(root_prim.GetPrim())

        # 2. Add Chassis (Fixed Base or Floating Base)
        # We start with a flat hierarchy to avoid XformStack errors in PhysX
        chassis_path = f"{root_path}/Chassis"
        self._add_link(stage, chassis_path, "chassis_kit", mass_kg=2.0, sku=sku, is_root=True)
        
        # Dimensions
        # Ideally passed from robot_data, using hardcoded defaults for now if missing
        # Note: CAD service generates legs based on 100mm, so we match that here.
        femur_len = 0.1  
        
        # Hip Offsets (Distance from center of chassis to hip joint)
        body_l = 0.24 
        body_w = 0.12
        hip_off_x = body_l / 2.0
        hip_off_y = body_w / 2.0
        
        legs = [
            {"name": "FR", "x": 1, "y": -1},
            {"name": "FL", "x": 1, "y": 1},
            {"name": "RR", "x": -1, "y": -1},
            {"name": "RL", "x": -1, "y": 1}
        ]

        for leg in legs:
            prefix = leg["name"]
            
            # --- A. FEMUR ---
            # Position: Placed at the Hip location relative to Root
            femur_path = f"{root_path}/Femur_{prefix}"
            hip_world_pos = Gf.Vec3f(leg['x'] * hip_off_x, leg['y'] * hip_off_y, 0)
            
            self._add_link(stage, femur_path, "femur_leg", mass_kg=0.2, pos=hip_world_pos, sku=sku)
            
            # Hip Joint (Connects Chassis -> Femur)
            # We define the joint INSIDE the Child (Femur)
            self._add_revolute_joint(
                stage, 
                joint_path=f"{femur_path}/Joint_Hip_{prefix}",
                body0_path=chassis_path, 
                body1_path=femur_path,
                # Pos0: Where is the pivot on the Parent (Chassis)? -> At the hip corner
                pos0=hip_world_pos, 
                # Pos1: Where is the pivot on the Child (Femur)? -> At its origin (0,0,0)
                pos1=Gf.Vec3f(0, 0, 0),
                axis="y",
                limit=(-45, 45),
                stiffness=10000.0
            )

            # --- B. TIBIA ---
            # Position: Placed at the Knee location relative to Root
            # Knee is at Hip + Femur Length (along X axis for neutral pose)
            tibia_path = f"{root_path}/Tibia_{prefix}"
            knee_world_pos = hip_world_pos + Gf.Vec3f(femur_len, 0, 0)
            
            self._add_link(stage, tibia_path, "tibia_leg", mass_kg=0.15, pos=knee_world_pos, sku=sku)
            
            # Knee Joint (Connects Femur -> Tibia)
            self._add_revolute_joint(
                stage,
                joint_path=f"{tibia_path}/Joint_Knee_{prefix}",
                body0_path=femur_path,
                body1_path=tibia_path,
                # Pos0: Pivot on Parent (Femur) -> At the end of the femur
                pos0=Gf.Vec3f(femur_len, 0, 0),
                # Pos1: Pivot on Child (Tibia) -> At its origin
                pos1=Gf.Vec3f(0, 0, 0),
                axis="y",
                limit=(-120, 0),
                stiffness=10000.0
            )

        stage.GetRootLayer().Save()
        print(f"   ⚡ Generated Articulated USD (Flat Hierarchy): {stage_path}")
        return stage_path

    def _add_link(self, stage, path, stl_key, mass_kg, pos=Gf.Vec3f(0,0,0), sku="robot_dog", is_root=False):
        """Adds a Rigid Body Mesh (Link)."""
        xform = UsdGeom.Xform.Define(stage, path)
        xform.AddTranslateOp().Set(pos)
        
        # Physics API
        rigid_api = UsdPhysics.RigidBodyAPI.Apply(xform.GetPrim())
        rigid_api.CreateRigidBodyEnabledAttr(True)
        
        mass_api = UsdPhysics.MassAPI.Apply(xform.GetPrim())
        mass_api.CreateMassAttr(mass_kg)
        
        # Visual Mesh
        mesh_path = f"{path}/Visual"
        mesh_filename = f"{sku}_{stl_key}.obj"
        mesh_abs_path = os.path.join(ASSETS_DIR, mesh_filename)
        
        if os.path.exists(mesh_abs_path):
            try:
                # Embed Geometry
                tm_mesh = trimesh.load(mesh_abs_path)
                if isinstance(tm_mesh, trimesh.Scene):
                    tm_mesh = trimesh.util.concatenate(tm_mesh.dump())

                usd_mesh = UsdGeom.Mesh.Define(stage, mesh_path)
                usd_mesh.CreatePointsAttr(tm_mesh.vertices)
                usd_mesh.CreateFaceVertexCountsAttr([3] * len(tm_mesh.faces))
                usd_mesh.CreateFaceVertexIndicesAttr(tm_mesh.faces.flatten())
                usd_mesh.CreateDisplayColorAttr([Gf.Vec3f(0.5, 0.5, 0.5)])
                
                # COLLISION FIX: Explicitly set approximation to convexHull
                # This fixes the "triangle mesh collision cannot be dynamic" error
                coll_api = UsdPhysics.CollisionAPI.Apply(usd_mesh.GetPrim())
                mesh_coll_api = UsdPhysics.MeshCollisionAPI.Apply(usd_mesh.GetPrim())
                mesh_coll_api.CreateApproximationAttr("convexHull")
                
            except Exception as e:
                print(f"      ❌ Failed to embed mesh {mesh_filename}: {e}")
                self._create_fallback_cube(stage, mesh_path)
        else:
            print(f"      ⚠️ Missing Mesh File: {mesh_filename}")
            self._create_fallback_cube(stage, mesh_path)

    def _create_fallback_cube(self, stage, path):
        cube = UsdGeom.Cube.Define(stage, path)
        cube.CreateSizeAttr(0.05)
        # Collision for fallback
        coll_api = UsdPhysics.CollisionAPI.Apply(cube.GetPrim())
        # Cubes don't need MeshCollisionAPI approximation, standard collision works

    def _add_revolute_joint(self, stage, joint_path, body0_path, body1_path, pos0, pos1, axis, limit, stiffness):
        joint = UsdPhysics.RevoluteJoint.Define(stage, joint_path)
        
        # Define Relationship Targets
        joint.CreateBody0Rel().AddTarget(body0_path)
        joint.CreateBody1Rel().AddTarget(body1_path)
        
        # Define Pivot Frames (Relative to Body0 and Body1)
        joint.CreateLocalPos0Attr().Set(pos0) 
        joint.CreateLocalRot0Attr().Set(Gf.Quatf(1,0,0,0))
        
        joint.CreateLocalPos1Attr().Set(pos1)
        joint.CreateLocalRot1Attr().Set(Gf.Quatf(1,0,0,0))
        
        # Axis and Limits
        joint.CreateAxisAttr(axis)
        joint.CreateLowerLimitAttr(limit[0])
        joint.CreateUpperLimitAttr(limit[1])
        
        # Drive
        driveAPI = UsdPhysics.DriveAPI.Apply(joint.GetPrim(), "angular")
        driveAPI.CreateTypeAttr("force") 
        driveAPI.CreateStiffnessAttr(stiffness) 
        driveAPI.CreateDampingAttr(stiffness / 10.0) 
        driveAPI.CreateTargetPositionAttr(0.0)