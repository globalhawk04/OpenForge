// FILE: cad/library.scad

module pro_frame(wheelbase_mm) {
    arm_len = (wheelbase_mm / 2) * 1.414;
    color([0.2, 0.2, 0.2]) {
        // Body
        translate([-20, -60, 0]) cube([40, 120, 4]);
        // Arms
        rotate([0,0,45]) translate([-2, -arm_len/2, 0]) cube([4, arm_len, 4]);
        rotate([0,0,-45]) translate([-2, -arm_len/2, 0]) cube([4, arm_len, 4]);
    }
}

module pro_motor(size_code) {
    color([0.1, 0.1, 0.1]) {
        cylinder(h=15, r=14, $fn=30); // Bell
        translate([0,0,-2]) cylinder(h=2, r=5, $fn=20); // Shaft base
    }
}

module pro_prop(diam_inch) {
    radius_mm = (diam_inch * 25.4) / 2;
    color([1, 0.5, 0, 0.5]) {
        cylinder(h=2, r=radius_mm, $fn=40); // Simple disc representation
        cylinder(h=8, r=3, $fn=20); // Hub
    }
}

module pro_stack(mount_mm, is_digital) {
    color([0.1, 0.3, 0.8]) {
        translate([-mount_mm/2, -mount_mm/2, 0]) cube([mount_mm, mount_mm, 8]); // ESC
        translate([-mount_mm/2, -mount_mm/2, 10]) cube([mount_mm, mount_mm, 5]); // FC
    }
}

module pro_battery(cells, capacity) {
    h = cells * 8;
    l = 70 + (capacity/1000)*10;
    color([0.1, 0.1, 0.1]) {
        cube([40, l, h]);
    }
}

module pro_camera(width) {
    color([0.1, 0.1, 0.1]) cube([width, width, width]);
}

module pro_companion_computer() {
    color([0, 0.8, 0]) {
        // PCB
        cube([85, 56, 2]); 
        // Heatsink
        translate([5, 5, 2]) color([0.2,0.2,0.2]) cube([40, 40, 15]);
        // Ports
        translate([80, 10, 2]) color([0.8,0.8,0.8]) cube([10, 10, 6]);
    }
}