/*
 * Title        : memory-out-experiment.c
 *              :
 * Compile      :
 * Capabilities : clang-morello -g -o memory-out-experiment memory-out-experiment.c -lm
 *              :
 * run          : ./memory-out-experiment
 *
 */


#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#define MIN_BLOCK_SIZE (1024 * 1024 * 100) // 100 MB
#define MAX_BLOCK_SIZE (1024 * 1024 * 1000) // 1 GB
#define BLOCK_STEP (1024 * 1024 * 100) // 100 MB per step
#define ITERATIONS 1000000  // Defining 1 million iterations for write/read


void perform_test(int num_of_trials, size_t block_size, FILE *log_file) {
    /* for (int test = 0; test < NUM_TESTS; test++) { */
    for (int trial = 0; trial < num_of_trials; trial++) {
        struct timespec start, end;
        double allocation_time, write_time, read_time, free_time;

        // Allocation
        clock_gettime(CLOCK_MONOTONIC, &start);
        char *block = (char *)malloc(block_size);
        clock_gettime(CLOCK_MONOTONIC, &end);
        if (block == NULL) {
            fprintf(log_file, "%zu,%d,Allocation failed,,,,\n", block_size / (1024 * 1024), trial + 1);
            return;
        }
        allocation_time = ((end.tv_sec - start.tv_sec) * 1000.0) + ((end.tv_nsec - start.tv_nsec) / 1e6);

        // Write
        clock_gettime(CLOCK_MONOTONIC, &start);
        for (size_t i = 0; i < block_size; i++) {
            for (int j = 0; j < ITERATIONS / block_size; j++) {
                block[i] = (char)(i % 256);
            }
        }
        clock_gettime(CLOCK_MONOTONIC, &end);
        write_time = ((end.tv_sec - start.tv_sec) * 1000.0) + ((end.tv_nsec - start.tv_nsec) / 1e6);

        // Read
        clock_gettime(CLOCK_MONOTONIC, &start);
        volatile char temp;
        for (size_t i = 0; i < block_size; i++) {
            for (int j = 0; j < ITERATIONS / block_size; j++) {
                temp = block[i];
            }
        }
        clock_gettime(CLOCK_MONOTONIC, &end);
        read_time = ((end.tv_sec - start.tv_sec) * 1000.0) + ((end.tv_nsec - start.tv_nsec) / 1e6);

        // Free
        clock_gettime(CLOCK_MONOTONIC, &start);
        free(block);
        clock_gettime(CLOCK_MONOTONIC, &end);
        free_time = ((end.tv_sec - start.tv_sec) * 1000.0) + ((end.tv_nsec - start.tv_nsec) / 1e6);

        // Log the times in CSV format
        fprintf(log_file, "%zu,%d,%.3f,%.3f,%.3f,%.3f\n",
                block_size / (1024 * 1024), trial + 1, allocation_time, write_time, read_time, free_time);
    }
}

int main() {
  
    time_t t;   
    time(&t);

 
    int num_of_trials= 0; /* number of repetitions of each operation */
    struct timespec start_time, end_time;
    clock_gettime(CLOCK_MONOTONIC, &start_time); // Start time

    num_of_trials=100;
    printf("Each operation will be executed %d times \n", num_of_trials);

    FILE *log_file = fopen("memory-out-experiment-results.csv", "w");
    if (log_file == NULL) {
        printf("Failed to open log file\n");
        return 1;
    }
    else {
        printf("csv file has been created and is now ready for collecting results!\n");
    }


    // Write CSV header
    fprintf(log_file, "Block Size (MB),Trial Num,Allocation Time (ms),Write Time (ms),Read Time (ms),Free Time (ms)\n");

    printf("\nThis program has been launched at (date and time): %s", ctime(&t));
    printf(" \nmemory allocate, write, read, free in execution now (no cheri compartments) ...\n");

    for (size_t block_size = MIN_BLOCK_SIZE; block_size <= MAX_BLOCK_SIZE; block_size += BLOCK_STEP) {
        perform_test(num_of_trials, block_size, log_file);
    }

    fclose(log_file);

    clock_gettime(CLOCK_MONOTONIC, &end_time); // End time

    double total_execution_time = ((end_time.tv_sec - start_time.tv_sec) * 1000.0) +
                                  ((end_time.tv_nsec - start_time.tv_nsec) / 1e6);

    // Log the total execution time to the file
    log_file = fopen("memory-out-experiment-results.csv", "a");
    if (log_file != NULL) {
        fprintf(log_file, "\nTotal execution time: %.3f milliseconds\n", total_execution_time);
        fclose(log_file);
    }
    return 0;
}
