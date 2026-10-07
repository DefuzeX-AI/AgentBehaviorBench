// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "LJsonObject.generated.h"

/**
 * 
 */
UCLASS()
class UE5PROJECT_API ULJsonObject : public UObject
{
	GENERATED_BODY()
	
public:
	
	
protected:
	TSharedPtr<FJsonObject> JsonObject;
	
};
