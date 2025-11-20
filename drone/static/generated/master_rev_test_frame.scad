
    use </home/j/Desktop/viz_it/drone/cad/library.scad>;
    $fn=50;
    union() {
        frame_body(269.0, 2.5);
        translate([95.0915, 95.0915, 0]) motor_mount(30.5, 2, 4.0);
        translate([- 95.0915, 95.0915, 0]) motor_mount(30.5, 2, 4.0);
        translate([- 95.0915, - 95.0915, 0]) motor_mount(30.5, 2, 4.0);
        translate([95.0915, - 95.0915, 0]) motor_mount(30.5, 2, 4.0);
        translate([0,0,2.5]) fc_mount(25.5);
    }
    