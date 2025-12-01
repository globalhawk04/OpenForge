// FILE: cad/library.scad
// VERSION: 2.0 (Professional Grade)
// This library defines the physical DNA of the drone.
// It is used by OpenSCAD to generate both the visual model and the collision mesh.

$fn = 60; // High resolution rendering for smooth curves

// --- UTILITY MODULES ---

module rounded_plate(size, r, h) {
    // Creates a rectangular plate with rounded corners
    // size: [x, y]
    // r: corner radius
    // h: height/thickness
    hull() {
        translate([r, r, 0]) cylinder(r=r, h=h);
        translate([size[0]-r, r, 0]) cylinder(r=r, h=h);
        translate([size[0]-r, size[1]-r, 0]) cylinder(r=r, h=h);
        translate([r, size[1]-r, 0]) cylinder(r=r, h=h);
    }
}

module chamfered_arm(length, width, thickness) {
    // An arm with 45-degree chamfered edges for realism/aerodynamics
    intersection() {
        cube([length, width, thickness], center=true);
        rotate([45,0,0]) cube([length, width*1.5, thickness*1.5], center=true);
        rotate([-45,0,0]) cube([length, width*1.5, thickness*1.5], center=true);
    }
}

// --- COMPONENT MODULES (The "Organs") ---

module pro_motor(stator_size, kv) {
    // Generates a realistic motor based on stator size
    // stator_size: integer (e.g., 2207, 1404, 0802)
    
    // Heuristic: Extract diameter and height from the 4-digit code
    // 2207 -> width=22+6=28mm, height=7+8=15mm
    width = (stator_size >= 1000) ? floor(stator_size/100) + 6 : 10; 
    height = (stator_size >= 1000) ? (stator_size % 100) + 8 : 8;
    
    color("#222") union() {
        // Base Mount
        cylinder(r=width/2, h=2);
        
        // Stator/Windings (Copper internals)
        translate([0,0,2]) color("#b87333") cylinder(r=(width/2)-1, h=height-4);
        
        // Bell (Aluminum housing)
        translate([0,0,2]) difference() {
            cylinder(r=width/2, h=height-3);
            // Cooling cutouts (visual flair)
            for(r=[0:60:360]) rotate([0,0,r]) translate([width/3, 0, 1]) cylinder(r=2, h=10);
        }
        
        // Shaft
        translate([0,0,height-1]) cylinder(r=2.5, h=5); 
        // Prop Nut (Nylock)
        translate([0,0,height+3]) color("silver") cylinder(r=3, h=3, $fn=6); 
    }
}

module pro_stack(mounting_pattern, is_analog) {
    // Represents FC + ESC Stack + Capacitor
    // mounting_pattern: 16, 20, 25.5, 30.5
    
    size = mounting_pattern + 5; // Board size is usually mount + padding
    
    union() {
        // ESC (Bottom Board - 4in1)
        color("#1a1a1a") translate([0,0,2]) cube([size, size, 4], center=true);
        
        // FC (Top Board)
        color("#3b4cca") translate([0,0,8]) {
            difference() {
                cube([size, size, 2], center=true);
                // Mounting holes
                for(x=[-1,1]) for(y=[-1,1])
                    translate([x*mounting_pattern/2, y*mounting_pattern/2, 0]) cylinder(r=1.5, h=10, center=true);
            }
        }
        
        // Steel Standoffs
        color("silver") for(x=[-1,1]) for(y=[-1,1])
            translate([x*mounting_pattern/2, y*mounting_pattern/2, 0]) cylinder(r=1.5, h=10);
            
        // Capacitor (Low ESR) - Critical for clean video
        color("gold") translate([-size/2, -size/2, 4]) rotate([90,0,0]) cylinder(r=4, h=12);
        
        // XT60 Pigtail/Pad
        color("#eee") translate([size/2, 0, 2]) cube([6, 8, 4], center=true);
    }
}

module pro_camera(width, type="digital") {
    // Accurate camera dimensions for collision testing
    // type: "digital" (Deep) or "analog" (Shallow)
    
    lens_r = width/2.5;
    depth = (type=="digital" || type=="true") ? 25 : 15;
    
    union() {
        // Main Sensor Body
        color("#222") translate([-width/2, -width/2, 0]) rounded_plate([width, width], 2, width);
        
        // Lens Housing
        color("#111") translate([0, -width/2, width/2]) rotate([90,0,0]) cylinder(r=lens_r, h=5);
        
        // Glass Element
        color("#000055") translate([0, -width/2 - 2, width/2]) rotate([90,0,0]) cylinder(r=lens_r*0.6, h=1);
        
        // Rear Heatsink (if digital/O3)
        if(type == "digital" || type == "true") {
            color("silver") translate([-width/2 + 2, 5, 2]) cube([width-4, depth, width-4]);
        }
    }
}

module pro_prop(diameter_inch, pitch_inch, blade_count) {
    // Visualizes the propeller swept volume
    diam_mm = diameter_inch * 25.4;
    hub_r = 2.5;
    
    color("cyan", 0.6) union() {
        // Hub
        cylinder(r=hub_r + 2, h=5, center=true);
        
        // Blades
        for(i=[0 : 360/blade_count : 360]) {
            rotate([0,0,i]) 
            translate([diam_mm/4, 0, 0]) 
            rotate([pitch_inch * 2, 0, 0]) // Visual twist based on pitch
                cube([diam_mm/2, diam_mm/8, 1.5], center=true);
        }
    }
}

module pro_battery(cells, capacity_mah) {
    // Parametric battery sizing based on density heuristics
    // 1000mah cell approx = 25mm length contribution?
    // Just a visual approximation
    
    l = (capacity_mah / 1000) * 25 + 30; 
    w = 35; // Standard width
    h = cells * 8; // approx 8mm per cell height
    
    union() {
        // Main Pack
        color("#333") translate([-l/2, -w/2, 0]) rounded_plate([l, w], 3, h);
        // Yellow Label
        color("yellow") translate([-l/2 + 5, -w/2 + 5, h]) cube([l-10, w-10, 0.1]);
        // Discharge Lead
        color("red") translate([l/2, 0, h/2]) rotate([0,90,0]) cylinder(r=2, h=10);
    }
}

// --- FRAME GENERATOR (The "Skeleton") ---

module pro_frame(wheelbase, arm_thick, plate_thick, stack_mounting) {
    // Generates a freestyle geometry frame dynamically
    
    // Calculate Arm Geometry from Wheelbase
    arm_len = (wheelbase / 2) * 1.414;
    
    // Body size depends on the stack size
    body_l = stack_mounting + 40;
    body_w = stack_mounting + 20;
    standoff_h = 25; // Standard freestyle deck height
    
    // 1. Arms (Individual components, replaceable)
    color("#111") for(i=[45, 135, 225, 315]) {
        rotate([0,0,i]) translate([0, -5, 0]) 
            chamfered_arm(arm_len/2 + 15, 10, arm_thick);
    }
    
    // 2. Bottom Plate (Sandwich)
    color("#1a1a1a") translate([0,0,arm_thick/2 + plate_thick/2]) 
        translate([-body_l/2, -body_w/2, 0])
            difference() {
                rounded_plate([body_l, body_w], 5, plate_thick);
                // Weight reduction cutout
                translate([body_l/2, body_w/2, -1]) cylinder(r=5, h=10);
            }

    // 3. Top Plate (Deck)
    color("#1a1a1a") translate([0,0,arm_thick + standoff_h]) 
        translate([-body_l/2, -body_w/2, 0])
            difference() {
                rounded_plate([body_l, body_w], 5, plate_thick);
                // Battery Strap Slots
                translate([body_l/2 - 2, body_w/2, -1]) cube([4, 20, 10], center=true);
            }
            
    // 4. Knurled Standoffs (Gold/Aluminum)
    color("gold") {
        translate([body_l/2 - 5, body_w/2 - 5, arm_thick]) cylinder(r=2.5, h=standoff_h);
        translate([-body_l/2 + 5, body_w/2 - 5, arm_thick]) cylinder(r=2.5, h=standoff_h);
        translate([-body_l/2 + 5, -body_w/2 + 5, arm_thick]) cylinder(r=2.5, h=standoff_h);
        translate([body_l/2 - 5, -body_w/2 + 5, arm_thick]) cylinder(r=2.5, h=standoff_h);
    }
}