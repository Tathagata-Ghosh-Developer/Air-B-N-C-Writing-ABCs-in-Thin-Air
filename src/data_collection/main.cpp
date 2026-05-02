// #include <Arduino_LSM9DS1.h>

// unsigned long startTime = 0;

// void setup() {

//   Serial.begin(115200);

//   delay(2000);

//   if (!IMU.begin()) {

//     while (1);
//   }

//   startTime = millis();
// }

// void loop() {

//   float ax, ay, az;
//   float gx, gy, gz;
//   float mx, my, mz;

//   if (IMU.accelerationAvailable() &&
//       IMU.gyroscopeAvailable() &&
//       IMU.magneticFieldAvailable()) {

//     // Read sensors
//     IMU.readAcceleration(ax, ay, az);
//     IMU.readGyroscope(gx, gy, gz);
//     IMU.readMagneticField(mx, my, mz);

//     unsigned long t = millis() - startTime;

//     // CSV FORMAT
//     Serial.print(t);
//     Serial.print(",");

//     // Accelerometer
//     Serial.print(ax, 6);
//     Serial.print(",");

//     Serial.print(ay, 6);
//     Serial.print(",");

//     Serial.print(az, 6);
//     Serial.print(",");

//     // Gyroscope
//     Serial.print(gx, 6);
//     Serial.print(",");

//     Serial.print(gy, 6);
//     Serial.print(",");

//     Serial.print(gz, 6);
//     Serial.print(",");

//     // Magnetometer
//     Serial.print(mx, 6);
//     Serial.print(",");

//     Serial.print(my, 6);
//     Serial.print(",");

//     Serial.println(mz, 6);
//   }

//   delay(10); // ~100 Hz
// }



// #include <Arduino.h>
// #include "rf_model.h"

// // IMPORTANT
// // Replace with your actual feature count
// #define FEATURE_COUNT 195

// // Create model object
// Eloquent::ML::Port::RandomForest clf;

// float features[FEATURE_COUNT];

// void setup() {

//     Serial.begin(115200);

//     while (!Serial);

//     Serial.println("RandomForest model loaded!");

//     // Dummy values
//     for (int i = 0; i < FEATURE_COUNT; i++) {
//         features[i] = 0.1;
//     }

//     int prediction = clf.predict(features);

//     Serial.print("Prediction: ");
//     Serial.println(prediction);
// }

// void loop() {

// }

// #include <Arduino.h>
// #include <Arduino_LSM9DS1.h>

// #include "rf_model.h"
// #include "scaler_params.h"

// #define WINDOW_SIZE 100
// #define AXES 9

// float imu_buffer[WINDOW_SIZE][AXES];

// float features[195];

// int sample_index = 0;

// bool recording = false;

// Eloquent::ML::Port::RandomForest clf;


// // =====================================================
// // FEATURE EXTRACTION
// // =====================================================

// void compute_features() {

//     int feature_idx = 0;

//     // =====================================
//     // CLEAR FEATURE ARRAY
//     // =====================================

//     for (int i = 0; i < 195; i++) {

//         features[i] = 0;
//     }

//     // =====================================================
//     // PER-AXIS FEATURES
//     // =====================================================

//     for (int axis = 0; axis < AXES; axis++) {

//         float values[WINDOW_SIZE];

//         float sum = 0;

//         float min_val = 99999;

//         float max_val = -99999;

//         float energy = 0;

//         // ---------------------------------
//         // COPY VALUES
//         // ---------------------------------

//         for (int i = 0; i < WINDOW_SIZE; i++) {

//             float v = imu_buffer[i][axis];

//             values[i] = v;

//             sum += v;

//             energy += v * v;

//             if (v < min_val) min_val = v;

//             if (v > max_val) max_val = v;
//         }

//         // ---------------------------------
//         // MEAN
//         // ---------------------------------

//         float mean = sum / WINDOW_SIZE;

//         // ---------------------------------
//         // STD
//         // ---------------------------------

//         float variance = 0;

//         for (int i = 0; i < WINDOW_SIZE; i++) {

//             float diff = values[i] - mean;

//             variance += diff * diff;
//         }

//         float stddev = sqrt(variance / WINDOW_SIZE);

//         // ---------------------------------
//         // MEDIAN
//         // ---------------------------------

//         for (int i = 0; i < WINDOW_SIZE - 1; i++) {

//             for (int j = 0; j < WINDOW_SIZE - i - 1; j++) {

//                 if (values[j] > values[j + 1]) {

//                     float temp = values[j];

//                     values[j] = values[j + 1];

//                     values[j + 1] = temp;
//                 }
//             }
//         }

//         float median = values[WINDOW_SIZE / 2];

//         // ---------------------------------
//         // DIFF FEATURES
//         // ---------------------------------

//         float diff_sum = 0;

//         for (int i = 1; i < WINDOW_SIZE; i++) {

//             diff_sum += abs(
//                 imu_buffer[i][axis] -
//                 imu_buffer[i - 1][axis]
//             );
//         }

//         float diff_mean =
//             diff_sum / (WINDOW_SIZE - 1);

//         float diff_var = 0;

//         for (int i = 1; i < WINDOW_SIZE; i++) {

//             float d = abs(
//                 imu_buffer[i][axis] -
//                 imu_buffer[i - 1][axis]
//             );

//             diff_var +=
//                 (d - diff_mean) *
//                 (d - diff_mean);
//         }

//         float diff_std =
//             sqrt(diff_var / (WINDOW_SIZE - 1));

//         // ---------------------------------
//         // STORE FEATURES
//         // ---------------------------------

//         features[feature_idx++] = mean;
//         features[feature_idx++] = stddev;
//         features[feature_idx++] = min_val;
//         features[feature_idx++] = max_val;
//         features[feature_idx++] = median;

//         // skew placeholder
//         features[feature_idx++] = 0;

//         // kurtosis placeholder
//         features[feature_idx++] = 0;

//         features[feature_idx++] = energy;

//         // p25 placeholder
//         features[feature_idx++] = 0;

//         // p75 placeholder
//         features[feature_idx++] = 0;

//         features[feature_idx++] = diff_mean;
//         features[feature_idx++] = diff_std;

//         // FFT placeholders
//         features[feature_idx++] = 0;
//         features[feature_idx++] = 0;
//         features[feature_idx++] = 0;
//     }

//     // =====================================================
//     // MAGNITUDE FEATURES
//     // =====================================================

//     float acc_mag[WINDOW_SIZE];

//     float gyro_mag[WINDOW_SIZE];

//     float mag_mag[WINDOW_SIZE];

//     for (int i = 0; i < WINDOW_SIZE; i++) {

//         float ax = imu_buffer[i][0];
//         float ay = imu_buffer[i][1];
//         float az = imu_buffer[i][2];

//         float gx = imu_buffer[i][3];
//         float gy = imu_buffer[i][4];
//         float gz = imu_buffer[i][5];

//         float mx = imu_buffer[i][6];
//         float my = imu_buffer[i][7];
//         float mz = imu_buffer[i][8];

//         acc_mag[i] =
//             sqrt(ax * ax + ay * ay + az * az);

//         gyro_mag[i] =
//             sqrt(gx * gx + gy * gy + gz * gz);

//         mag_mag[i] =
//             sqrt(mx * mx + my * my + mz * mz);
//     }

//     float* mags[3] = {
//         acc_mag,
//         gyro_mag,
//         mag_mag
//     };

//     for (int m = 0; m < 3; m++) {

//         float sum = 0;

//         float min_val = 99999;

//         float max_val = -99999;

//         float energy = 0;

//         for (int i = 0; i < WINDOW_SIZE; i++) {

//             float v = mags[m][i];

//             sum += v;

//             energy += v * v;

//             if (v < min_val) min_val = v;

//             if (v > max_val) max_val = v;
//         }

//         float mean = sum / WINDOW_SIZE;

//         float variance = 0;

//         for (int i = 0; i < WINDOW_SIZE; i++) {

//             float d = mags[m][i] - mean;

//             variance += d * d;
//         }

//         float stddev =
//             sqrt(variance / WINDOW_SIZE);

//         features[feature_idx++] = mean;
//         features[feature_idx++] = stddev;
//         features[feature_idx++] = min_val;
//         features[feature_idx++] = max_val;

//         // median placeholder
//         features[feature_idx++] = 0;

//         features[feature_idx++] = energy;

//         // skew placeholder
//         features[feature_idx++] = 0;

//         // kurtosis placeholder
//         features[feature_idx++] = 0;
//     }

//     // =====================================================
//     // CORRELATION FEATURES
//     // =====================================================

//     for (int a = 0; a < AXES; a++) {

//         for (int b = a + 1; b < AXES; b++) {

//             float mean_a = 0;

//             float mean_b = 0;

//             for (int i = 0; i < WINDOW_SIZE; i++) {

//                 mean_a += imu_buffer[i][a];

//                 mean_b += imu_buffer[i][b];
//             }

//             mean_a /= WINDOW_SIZE;

//             mean_b /= WINDOW_SIZE;

//             float numerator = 0;

//             float denom_a = 0;

//             float denom_b = 0;

//             for (int i = 0; i < WINDOW_SIZE; i++) {

//                 float da =
//                     imu_buffer[i][a] - mean_a;

//                 float db =
//                     imu_buffer[i][b] - mean_b;

//                 numerator += da * db;

//                 denom_a += da * da;

//                 denom_b += db * db;
//             }

//             float denominator =
//                 sqrt(denom_a * denom_b);

//             float corr = 0;

//             if (denominator > 0.000001) {

//                 corr = numerator / denominator;
//             }

//             features[feature_idx++] = corr;
//         }
//     }

//     // =====================================
//     // DEBUG FEATURE COUNT
//     // =====================================

//     Serial.print("Feature count: ");

//     Serial.println(feature_idx);
// }


// // =====================================================
// // NORMALIZATION
// // =====================================================

// void normalize_features() {

//     for (int i = 0; i < 195; i++) {

//         if (feature_scales[i] != 0) {

//             features[i] =
//                 (features[i] - feature_means[i]) /
//                 feature_scales[i];
//         }
//     }
// }


// // =====================================================
// // SETUP
// // =====================================================

// void setup() {

//     Serial.begin(115200);

//     while (!Serial);

//     if (!IMU.begin()) {

//         Serial.println("IMU init failed!");

//         while (1);
//     }

//     Serial.println("IMU ready.");
// }


// // =====================================================
// // LOOP
// // =====================================================

// void loop() {

//     float ax, ay, az;

//     float gx, gy, gz;

//     float mx, my, mz;

//     // ==========================================
//     // SERIAL COMMANDS
//     // ==========================================

//     if (Serial.available()) {

//         char cmd = Serial.read();

//         // --------------------------------------
//         // START RECORDING
//         // --------------------------------------

//         if (cmd == 's') {

//             recording = true;

//             sample_index = 0;

//             Serial.println("RECORDING STARTED");
//         }

//         // --------------------------------------
//         // END RECORDING
//         // --------------------------------------

//         if (cmd == 'e') {

//             recording = false;

//             Serial.println("RECORDING ENDED");

//             if (sample_index > 20) {

//                 // ----------------------------------
//                 // FEATURE EXTRACTION
//                 // ----------------------------------

//                 compute_features();

//                 // ----------------------------------
//                 // TEMPORARILY DISABLED
//                 // FOR DEBUGGING
//                 // ----------------------------------

//                 // normalize_features();

//                 // ----------------------------------
//                 // INFERENCE
//                 // ----------------------------------

//                 Serial.println("RUNNING INFERENCE");

//                 int prediction =
//                     clf.predict(features);

//                 Serial.print("PREDICTION: ");

//                 Serial.println(prediction);

//                 Serial.print("Samples: ");

//                 Serial.println(sample_index);
//             }

//             else {

//                 Serial.println("NOT ENOUGH DATA");
//             }

//             sample_index = 0;
//         }
//     }

//     // ==========================================
//     // RECORD DATA
//     // ==========================================

//     if (recording) {

//         if (
//             IMU.accelerationAvailable() &&
//             IMU.gyroscopeAvailable() &&
//             IMU.magneticFieldAvailable()
//         ) {

//             IMU.readAcceleration(ax, ay, az);

//             IMU.readGyroscope(gx, gy, gz);

//             IMU.readMagneticField(mx, my, mz);

//             if (sample_index < WINDOW_SIZE) {

//                 imu_buffer[sample_index][0] = ax;
//                 imu_buffer[sample_index][1] = ay;
//                 imu_buffer[sample_index][2] = az;

//                 imu_buffer[sample_index][3] = gx;
//                 imu_buffer[sample_index][4] = gy;
//                 imu_buffer[sample_index][5] = gz;

//                 imu_buffer[sample_index][6] = mx;
//                 imu_buffer[sample_index][7] = my;
//                 imu_buffer[sample_index][8] = mz;

//                 sample_index++;
//             }
//         }
//     }

//     delay(10);
// }


#include <Arduino.h>
#include <Arduino_LSM9DS1.h>

#include "rf_model.h"
#include "scaler_params.h"

#define WINDOW_SIZE 100
#define AXES 9

float imu_buffer[WINDOW_SIZE][AXES];

float features[195];

int sample_index = 0;

bool recording = false;

Eloquent::ML::Port::RandomForest clf;


// =====================================================
// SKEW
// =====================================================

float compute_skew(float values[], float mean, float stddev) {

    if (stddev < 1e-6)
        return 0;

    float skew = 0;

    for (int i = 0; i < WINDOW_SIZE; i++) {

        float z = (values[i] - mean) / stddev;

        skew += z * z * z;
    }

    return skew / WINDOW_SIZE;
}


// =====================================================
// KURTOSIS
// =====================================================

float compute_kurtosis(float values[], float mean, float stddev) {

    if (stddev < 1e-6)
        return 0;

    float kurt = 0;

    for (int i = 0; i < WINDOW_SIZE; i++) {

        float z = (values[i] - mean) / stddev;

        kurt += z * z * z * z;
    }

    return kurt / WINDOW_SIZE;
}


// =====================================================
// FFT MEAN
// =====================================================

float compute_fft_mean(float values[]) {

    float fft_sum = 0;

    for (int k = 1; k < WINDOW_SIZE / 2; k++) {

        float real = 0;
        float imag = 0;

        for (int n = 0; n < WINDOW_SIZE; n++) {

            float angle =
                2.0 * PI * k * n / WINDOW_SIZE;

            real += values[n] * cos(angle);

            imag -= values[n] * sin(angle);
        }

        float mag = sqrt(real * real + imag * imag);

        fft_sum += mag;
    }

    return fft_sum / (WINDOW_SIZE / 2);
}


// =====================================================
// FFT STD
// =====================================================

float compute_fft_std(float values[], float fft_mean) {

    float variance = 0;

    for (int k = 1; k < WINDOW_SIZE / 2; k++) {

        float real = 0;
        float imag = 0;

        for (int n = 0; n < WINDOW_SIZE; n++) {

            float angle =
                2.0 * PI * k * n / WINDOW_SIZE;

            real += values[n] * cos(angle);

            imag -= values[n] * sin(angle);
        }

        float mag = sqrt(real * real + imag * imag);

        variance += (mag - fft_mean) * (mag - fft_mean);
    }

    return sqrt(variance / (WINDOW_SIZE / 2));
}


// =====================================================
// FFT MAX
// =====================================================

float compute_fft_max(float values[]) {

    float fft_max = 0;

    for (int k = 1; k < WINDOW_SIZE / 2; k++) {

        float real = 0;
        float imag = 0;

        for (int n = 0; n < WINDOW_SIZE; n++) {

            float angle =
                2.0 * PI * k * n / WINDOW_SIZE;

            real += values[n] * cos(angle);

            imag -= values[n] * sin(angle);
        }

        float mag = sqrt(real * real + imag * imag);

        if (mag > fft_max)
            fft_max = mag;
    }

    return fft_max;
}


// =====================================================
// FEATURE EXTRACTION
// =====================================================

void compute_features() {

    int feature_idx = 0;

    for (int i = 0; i < 195; i++) {

        features[i] = 0;
    }

    // =====================================================
    // PER AXIS FEATURES
    // =====================================================

    for (int axis = 0; axis < AXES; axis++) {

        float values[WINDOW_SIZE];

        float sum = 0;

        float min_val = 99999;

        float max_val = -99999;

        float energy = 0;

        // --------------------------------------
        // COPY VALUES
        // --------------------------------------

        for (int i = 0; i < WINDOW_SIZE; i++) {

            float v = imu_buffer[i][axis];

            values[i] = v;

            sum += v;

            energy += v * v;

            if (v < min_val)
                min_val = v;

            if (v > max_val)
                max_val = v;
        }

        // --------------------------------------
        // MEAN
        // --------------------------------------

        float mean = sum / WINDOW_SIZE;

        // --------------------------------------
        // STD
        // --------------------------------------

        float variance = 0;

        for (int i = 0; i < WINDOW_SIZE; i++) {

            float diff = values[i] - mean;

            variance += diff * diff;
        }

        float stddev = sqrt(variance / WINDOW_SIZE);

        // --------------------------------------
        // SORT FOR MEDIAN/PERCENTILES
        // --------------------------------------

        for (int i = 0; i < WINDOW_SIZE - 1; i++) {

            for (int j = 0; j < WINDOW_SIZE - i - 1; j++) {

                if (values[j] > values[j + 1]) {

                    float temp = values[j];

                    values[j] = values[j + 1];

                    values[j + 1] = temp;
                }
            }
        }

        float median = values[WINDOW_SIZE / 2];

        float p25 = values[WINDOW_SIZE / 4];

        float p75 = values[(3 * WINDOW_SIZE) / 4];

        // --------------------------------------
        // SKEW/KURTOSIS
        // --------------------------------------

        float skew =
            compute_skew(values, mean, stddev);

        float kurtosis =
            compute_kurtosis(values, mean, stddev);

        // --------------------------------------
        // ENERGY + DIFF
        // --------------------------------------

        float diff_sum = 0;

        for (int i = 1; i < WINDOW_SIZE; i++) {

            diff_sum += abs(
                imu_buffer[i][axis] -
                imu_buffer[i - 1][axis]
            );
        }

        float diff_mean =
            diff_sum / (WINDOW_SIZE - 1);

        float diff_var = 0;

        for (int i = 1; i < WINDOW_SIZE; i++) {

            float d = abs(
                imu_buffer[i][axis] -
                imu_buffer[i - 1][axis]
            );

            diff_var +=
                (d - diff_mean) *
                (d - diff_mean);
        }

        float diff_std =
            sqrt(diff_var / (WINDOW_SIZE - 1));

        // --------------------------------------
        // FFT
        // --------------------------------------

        float fft_mean =
            compute_fft_mean(values);

        float fft_std =
            compute_fft_std(values, fft_mean);

        float fft_max =
            compute_fft_max(values);

        // --------------------------------------
        // STORE FEATURES
        // --------------------------------------

        features[feature_idx++] = mean;
        features[feature_idx++] = stddev;
        features[feature_idx++] = min_val;
        features[feature_idx++] = max_val;
        features[feature_idx++] = median;
        features[feature_idx++] = skew;
        features[feature_idx++] = kurtosis;
        features[feature_idx++] = energy;
        features[feature_idx++] = p25;
        features[feature_idx++] = p75;
        features[feature_idx++] = diff_mean;
        features[feature_idx++] = diff_std;
        features[feature_idx++] = fft_mean;
        features[feature_idx++] = fft_std;
        features[feature_idx++] = fft_max;
    }

    // =====================================================
    // MAGNITUDE FEATURES
    // =====================================================

    float acc_mag[WINDOW_SIZE];
    float gyro_mag[WINDOW_SIZE];
    float mag_mag[WINDOW_SIZE];

    for (int i = 0; i < WINDOW_SIZE; i++) {

        float ax = imu_buffer[i][0];
        float ay = imu_buffer[i][1];
        float az = imu_buffer[i][2];

        float gx = imu_buffer[i][3];
        float gy = imu_buffer[i][4];
        float gz = imu_buffer[i][5];

        float mx = imu_buffer[i][6];
        float my = imu_buffer[i][7];
        float mz = imu_buffer[i][8];

        acc_mag[i] =
            sqrt(ax * ax + ay * ay + az * az);

        gyro_mag[i] =
            sqrt(gx * gx + gy * gy + gz * gz);

        mag_mag[i] =
            sqrt(mx * mx + my * my + mz * mz);
    }

    float* mags[3] = {
        acc_mag,
        gyro_mag,
        mag_mag
    };

    for (int m = 0; m < 3; m++) {

        float sum = 0;

        float min_val = 99999;

        float max_val = -99999;

        float energy = 0;

        float mag_values[WINDOW_SIZE];

        for (int i = 0; i < WINDOW_SIZE; i++) {

            float v = mags[m][i];

            mag_values[i] = v;

            sum += v;

            energy += v * v;

            if (v < min_val)
                min_val = v;

            if (v > max_val)
                max_val = v;
        }

        float mean = sum / WINDOW_SIZE;

        float variance = 0;

        for (int i = 0; i < WINDOW_SIZE; i++) {

            float d = mag_values[i] - mean;

            variance += d * d;
        }

        float stddev = sqrt(variance / WINDOW_SIZE);

        // SORT

        for (int i = 0; i < WINDOW_SIZE - 1; i++) {

            for (int j = 0; j < WINDOW_SIZE - i - 1; j++) {

                if (mag_values[j] > mag_values[j + 1]) {

                    float temp = mag_values[j];

                    mag_values[j] = mag_values[j + 1];

                    mag_values[j + 1] = temp;
                }
            }
        }

        float median =
            mag_values[WINDOW_SIZE / 2];

        float skew =
            compute_skew(mag_values, mean, stddev);

        float kurtosis =
            compute_kurtosis(mag_values, mean, stddev);

        features[feature_idx++] = mean;
        features[feature_idx++] = stddev;
        features[feature_idx++] = min_val;
        features[feature_idx++] = max_val;
        features[feature_idx++] = median;
        features[feature_idx++] = energy;
        features[feature_idx++] = skew;
        features[feature_idx++] = kurtosis;
    }

    // =====================================================
    // CORRELATION FEATURES
    // =====================================================

    for (int a = 0; a < AXES; a++) {

        for (int b = a + 1; b < AXES; b++) {

            float mean_a = 0;
            float mean_b = 0;

            for (int i = 0; i < WINDOW_SIZE; i++) {

                mean_a += imu_buffer[i][a];
                mean_b += imu_buffer[i][b];
            }

            mean_a /= WINDOW_SIZE;
            mean_b /= WINDOW_SIZE;

            float numerator = 0;
            float denom_a = 0;
            float denom_b = 0;

            for (int i = 0; i < WINDOW_SIZE; i++) {

                float da =
                    imu_buffer[i][a] - mean_a;

                float db =
                    imu_buffer[i][b] - mean_b;

                numerator += da * db;

                denom_a += da * da;

                denom_b += db * db;
            }

            float denominator =
                sqrt(denom_a * denom_b);

            float corr = 0;

            if (denominator > 1e-6)
                corr = numerator / denominator;

            features[feature_idx++] = corr;
        }
    }

    Serial.print("Feature count: ");
    Serial.println(feature_idx);
}


// =====================================================
// NORMALIZATION
// =====================================================

void normalize_features() {

    for (int i = 0; i < 195; i++) {

        if (feature_scales[i] != 0) {

            features[i] =
                (features[i] - feature_means[i]) /
                feature_scales[i];
        }
    }
}


// =====================================================
// SETUP
// =====================================================

void setup() {

    Serial.begin(115200);

    while (!Serial);

    if (!IMU.begin()) {

        Serial.println("IMU init failed!");

        while (1);
    }

    Serial.println("IMU ready.");
}


// =====================================================
// LOOP
// =====================================================

void loop() {

    float ax, ay, az;
    float gx, gy, gz;
    float mx, my, mz;

    // ==========================================
    // SERIAL COMMANDS
    // ==========================================

    if (Serial.available()) {

        char cmd = Serial.read();

        // --------------------------------------
        // START RECORDING
        // --------------------------------------

        if (cmd == 's') {

            recording = true;

            sample_index = 0;

            Serial.println("RECORDING STARTED");
        }

        // --------------------------------------
        // END RECORDING
        // --------------------------------------

        if (cmd == 'e') {

            recording = false;

            Serial.println("RECORDING ENDED");

            if (sample_index > 20) {

                compute_features();

                normalize_features();

                Serial.println("RUNNING INFERENCE");

                int prediction =
                    clf.predict(features);

                Serial.print("PREDICTION: ");

                Serial.println(prediction);

                Serial.print("Samples: ");

                Serial.println(sample_index);
            }

            else {

                Serial.println("NOT ENOUGH DATA");
            }

            sample_index = 0;
        }
    }

    // ==========================================
    // RECORD SENSOR DATA
    // ==========================================

    if (recording) {

        if (
            IMU.accelerationAvailable() &&
            IMU.gyroscopeAvailable() &&
            IMU.magneticFieldAvailable()
        ) {

            IMU.readAcceleration(ax, ay, az);

            IMU.readGyroscope(gx, gy, gz);

            IMU.readMagneticField(mx, my, mz);

            if (sample_index < WINDOW_SIZE) {

                imu_buffer[sample_index][0] = ax;
                imu_buffer[sample_index][1] = ay;
                imu_buffer[sample_index][2] = az;

                imu_buffer[sample_index][3] = gx;
                imu_buffer[sample_index][4] = gy;
                imu_buffer[sample_index][5] = gz;

                imu_buffer[sample_index][6] = mx;
                imu_buffer[sample_index][7] = my;
                imu_buffer[sample_index][8] = mz;

                sample_index++;
            }
        }
    }

    delay(10);
}

