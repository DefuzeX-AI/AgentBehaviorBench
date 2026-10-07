// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"

#include "ImageHelper.generated.h"

UCLASS()
class UE5PROJECT_API AImageHelper : public AActor
{
	GENERATED_BODY()

public:
	AImageHelper();

public:
	UFUNCTION(BlueprintCallable, Category = "HTTP|ImageUpload")
	FString GetImageJson(const FString& ImageName);


	void UploadImageWithJsonString(
		const FString& InUrl,
		const FString& InFileField,
		const FString& InFieldsJsonString,
		const FString& InFilePath,
		TFunction<void(bool bSucceed, const FString& ResponseMessage)> InCallback
	);

	/*







*/
	UFUNCTION(BlueprintCallable, Category = "HTTP|ImageUpload")
	void UploadBridgeTaskImage(
		const FString& InUrl,
		const FString& InFileField,
		const FString& InFieldsJsonString,
		const FString& InFilePath,
		bool& bOutSucceed,
		FString& OutMessage
	);

private:
	FString Boundary;
};