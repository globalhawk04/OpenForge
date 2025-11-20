
    use </home/j/Desktop/viz_it/drone/cad/library.scad>;
    $fn=50;
    union() {
        frame_body(77.0, 2.5);
        translate([27.2195, 27.2195, 0]) motor_mount(16.0, 2, 4.0);
        translate([- 27.2195, 27.2195, 0]) motor_mount(16.0, 2, 4.0);
        translate([- 27.2195, - 27.2195, 0]) motor_mount(16.0, 2, 4.0);
        translate([27.2195, - 27.2195, 0]) motor_mount(16.0, 2, 4.0);
        translate([0,0,2.5]) fc_mount(25.5);
    }
    