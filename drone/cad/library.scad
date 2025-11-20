// FILE: cad/library.scad

module motor_mount(bolt_spacing, shaft_hole, bolt_hole_size=2.2) {
    difference() {
        cylinder(h=3, r=(bolt_spacing/2) + 3, $fn=60);
        // Shaft hole
        translate([0,0,-1]) cylinder(h=5, r=shaft_hole/2, $fn=60);
        // Bolt holes (4-pattern)
        // Uses the dynamic bolt_hole_size passed from Python
        for(r=[0:90:270]) rotate([0,0,r]) 
            translate([bolt_spacing/2, 0, -1]) 
            cylinder(h=5, r=bolt_hole_size/2, $fn=20); 
    }
}

module fc_mount(spacing) {
    // 4 posts for the FC
    for(x=[-1,1]) for(y=[-1,1])
        translate([x*spacing/2, y*spacing/2, 0])
            cylinder(h=5, r=2, $fn=20);
}

module frame_body(wheelbase, arm_thickness) {
    // Simple X frame
    hull() {
        cylinder(h=arm_thickness, r=10);
        translate([wheelbase/2 * 0.707, wheelbase/2 * 0.707, 0]) cylinder(h=arm_thickness, r=5);
    }
    hull() {
        cylinder(h=arm_thickness, r=10);
        translate([-wheelbase/2 * 0.707, wheelbase/2 * 0.707, 0]) cylinder(h=arm_thickness, r=5);
    }
    hull() {
        cylinder(h=arm_thickness, r=10);
        translate([-wheelbase/2 * 0.707, -wheelbase/2 * 0.707, 0]) cylinder(h=arm_thickness, r=5);
    }
    hull() {
        cylinder(h=arm_thickness, r=10);
        translate([wheelbase/2 * 0.707, -wheelbase/2 * 0.707, 0]) cylinder(h=arm_thickness, r=5);
    }
}

// --- PROXIES FOR VISUALIZATION ---

module proxy_motor(stator_diam, height) {
    color("silver") cylinder(h=height, r=stator_diam/2);
    color("black") translate([0,0,height]) cylinder(h=5, r=1); // Shaft
}

module proxy_fc(mounting, size) {
    color("red") difference() {
        cube([size, size, 2], center=true);
        // Mounting holes
        for(x=[-1,1]) for(y=[-1,1])
            translate([x*mounting/2, y*mounting/2, 0]) cylinder(h=10, r=1.5, center=true);
    }
    // USB Port
    color("silver") translate([size/2, 0, 1]) cube([5, 8, 3], center=true);
}

module proxy_prop(diameter_mm) {
    hub_diam = 5;
    blade_len = (diameter_mm - hub_diam) / 2;
    
    color("cyan") union() {
        cylinder(h=4, r=hub_diam/2, center=true, $fn=20);
        rotate([0, 10, 0]) translate([blade_len/2 + hub_diam/2, 0, 0]) 
            cube([blade_len, 4, 1], center=true);
        rotate([0, 10, 180]) translate([blade_len/2 + hub_diam/2, 0, 0]) 
            cube([blade_len, 4, 1], center=true);
    }
}

module proxy_camera(width_mm) {
    depth = width_mm * 0.8;
    height = width_mm;
    union() {
        color("black") cube([width_mm, depth, height], center=true);
        color("gray") translate([0, -depth/2, 0]) 
            rotate([90, 0, 0]) 
            cylinder(h=5, r=width_mm/3, $fn=30);
    }
}

module proxy_battery(length, width, height) {
    union() {
        color("yellow") cube([width, length, height], center=true);
        color("red") translate([0, length/2, 0]) cube([3, 5, 2], center=true);
    }
}